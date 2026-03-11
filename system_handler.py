import logging
from core.connection_manager import ConnectionManager
from core.channel_registry import ChannelRegistry
from core.presence import PresenceTracker

logger = logging.getLogger(__name__)


class SystemHandler:
    def __init__(self, manager: ConnectionManager, registry: ChannelRegistry, presence: PresenceTracker):
        self.manager = manager
        self.registry = registry
        self.presence = presence

    async def on_join(self, conn_id: str, user, channel: str):
        # Notify channel members
        await self.registry.publish(
            channel,
            {
                "type": "user_joined",
                "channel": channel,
                "user": {"id": user.id, "name": user.display_name},
            },
            self.manager,
            exclude=conn_id,
        )

        # Send channel state to the joining user
        members = await self.registry.get_members(channel)
        online = [
            self.presence.get_presence(
                self.manager.get_connection(cid).user_id
            )
            for cid in members
            if self.manager.get_connection(cid)
        ]
        await self.manager.send(conn_id, {
            "type": "channel_state",
            "channel": channel,
            "member_count": len(members),
            "online_users": [u for u in online if u],
        })
        logger.info(f"User {user.id} joined #{channel}")

    async def on_leave(self, conn_id: str, user, channel: str):
        await self.registry.publish(
            channel,
            {
                "type": "user_left",
                "channel": channel,
                "user": {"id": user.id, "name": user.display_name},
            },
            self.manager,
        )
        logger.info(f"User {user.id} left #{channel}")
