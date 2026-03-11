"""
realtime-ws-server — WebSocket server for live notifications,
presence tracking, and pub/sub channels.
"""

import asyncio
import logging
import signal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.connection_manager import ConnectionManager
from core.channel_registry import ChannelRegistry
from core.presence import PresenceTracker
from core.rate_limiter import WsRateLimiter
from handlers.message_handler import MessageHandler
from handlers.system_handler import SystemHandler
from middleware.auth import authenticate_ws_token
from routers import channels, presence, admin
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

manager     = ConnectionManager()
registry    = ChannelRegistry()
presence    = PresenceTracker()
rate_limiter = WsRateLimiter(max_messages=60, window_seconds=10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.load_persistent_channels()
    await presence.start_heartbeat_loop()
    logger.info("Realtime server ready")
    yield
    await manager.disconnect_all()
    await presence.stop()
    logger.info("Realtime server shut down")


app = FastAPI(
    title="Realtime WebSocket Server",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(channels.router,  prefix="/api/channels",  tags=["Channels"])
app.include_router(presence.router,  prefix="/api/presence",  tags=["Presence"])
app.include_router(admin.router,     prefix="/api/admin",     tags=["Admin"])


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    channel: str = Query(default="general"),
):
    user = await authenticate_ws_token(token)
    if user is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    conn_id = await manager.connect(websocket, user_id=user.id, channel=channel)
    await presence.mark_online(user.id, conn_id, channel=channel)
    await registry.join(channel, conn_id)

    msg_handler    = MessageHandler(manager, registry, presence, rate_limiter)
    system_handler = SystemHandler(manager, registry, presence)

    await system_handler.on_join(conn_id, user, channel)

    try:
        while True:
            raw = await websocket.receive_json()
            await msg_handler.handle(conn_id, user, raw)
    except WebSocketDisconnect as exc:
        logger.info(f"Client {conn_id} disconnected (code={exc.code})")
    except Exception as exc:
        logger.exception(f"Unexpected error for {conn_id}: {exc}")
    finally:
        await manager.disconnect(conn_id)
        await registry.leave(channel, conn_id)
        await presence.mark_offline(user.id, conn_id)
        await system_handler.on_leave(conn_id, user, channel)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connections": manager.total_connections,
        "channels": registry.total_channels,
    }
