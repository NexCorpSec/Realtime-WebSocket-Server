import logging
from typing import Any, Dict
from core.connection_manager import ConnectionManager
from core.channel_registry import ChannelRegistry
from core.presence import PresenceTracker
from core.rate_limiter import WsRateLimiter

logger = logging.getLogger(__name__)

VALID_TYPES = {"message", "typing", "react", "subscribe", "unsubscribe", "ping"}


class MessageHandler:
    def __init__(
        self,
        manager: ConnectionManager,
        registry: ChannelRegistry,
        presence: PresenceTracker,
        rate_limiter: WsRateLimiter,
    ):
        self.manager = manager
        self.registry = registry
        self.presence = presence
        self.rate_limiter = rate_limiter

    async def handle(self, conn_id: str, user, raw: Dict[str, Any]):
        msg_type = raw.get("type")

        if msg_type not in VALID_TYPES:
            await self.manager.send(conn_id, {"type": "error", "code": "INVALID_TYPE", "detail": f"Unknown type '{msg_type}'"})
            return

        if not await self.rate_limiter.allow(conn_id):
            await self.manager.send(conn_id, {"type": "error", "code": "RATE_LIMITED", "detail": "Slow down"})
            return

        handler = getattr(self, f"_handle_{msg_type}", None)
        if handler:
            await handler(conn_id, user, raw)

    # ── Handlers ──────────────────────────────────────────

    async def _handle_message(self, conn_id: str, user, raw: dict):
        channel = raw.get("channel") or self.manager.get_connection(conn_id).channel
        text = str(raw.get("text", "")).strip()

        if not text:
            await self.manager.send(conn_id, {"type": "error", "code": "EMPTY_MESSAGE"})
            return
        if len(text) > 4000:
            await self.manager.send(conn_id, {"type": "error", "code": "MESSAGE_TOO_LONG"})
            return

        payload = {
            "type": "message",
            "channel": channel,
            "from": {"id": user.id, "name": user.display_name},
            "text": text,
            "ts": raw.get("ts"),
        }
        delivered = await self.registry.publish(channel, payload, self.manager, exclude=conn_id)
        await self.manager.send(conn_id, {"type": "ack", "ref": raw.get("ref"), "delivered": delivered})
        logger.debug(f"Message from {user.id} in #{channel}: {delivered} recipients")

    async def _handle_typing(self, conn_id: str, user, raw: dict):
        channel = raw.get("channel") or self.manager.get_connection(conn_id).channel
        await self.registry.publish(
            channel,
            {"type": "typing", "channel": channel, "user_id": user.id, "user_name": user.display_name},
            self.manager,
            exclude=conn_id,
        )

    async def _handle_react(self, conn_id: str, user, raw: dict):
        channel = raw.get("channel") or self.manager.get_connection(conn_id).channel
        await self.registry.publish(
            channel,
            {
                "type": "react",
                "channel": channel,
                "message_id": raw.get("message_id"),
                "emoji": raw.get("emoji"),
                "user_id": user.id,
            },
            self.manager,
            exclude=conn_id,
        )

    async def _handle_subscribe(self, conn_id: str, user, raw: dict):
        channel = raw.get("channel", "")
        if not channel:
            return
        joined = await self.registry.join(channel, conn_id)
        await self.manager.send(conn_id, {"type": "subscribed", "channel": channel, "ok": joined})

    async def _handle_unsubscribe(self, conn_id: str, user, raw: dict):
        channel = raw.get("channel", "")
        await self.registry.leave(channel, conn_id)
        await self.manager.send(conn_id, {"type": "unsubscribed", "channel": channel})

    async def _handle_ping(self, conn_id: str, user, raw: dict):
        await self.manager.send(conn_id, {"type": "pong", "ref": raw.get("ref")})
