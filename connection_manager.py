import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    id: str
    websocket: WebSocket
    user_id: str
    channel: str
    connected_at: float
    metadata: Dict = field(default_factory=dict)


class ConnectionManager:
    """
    Manages all active WebSocket connections.
    Thread-safe via asyncio lock.
    """

    def __init__(self):
        self._connections: Dict[str, Connection] = {}
        self._user_connections: Dict[str, set] = {}   # user_id → {conn_ids}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str, channel: str) -> str:
        await websocket.accept()
        conn_id = str(uuid.uuid4())

        async with self._lock:
            import time
            self._connections[conn_id] = Connection(
                id=conn_id,
                websocket=websocket,
                user_id=user_id,
                channel=channel,
                connected_at=time.time(),
            )
            self._user_connections.setdefault(user_id, set()).add(conn_id)

        logger.info(f"Connected: conn={conn_id} user={user_id} channel={channel}")
        return conn_id

    async def disconnect(self, conn_id: str):
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn:
                self._user_connections.get(conn.user_id, set()).discard(conn_id)
                if not self._user_connections.get(conn.user_id):
                    self._user_connections.pop(conn.user_id, None)
        logger.info(f"Disconnected: conn={conn_id}")

    async def disconnect_all(self):
        async with self._lock:
            for conn in list(self._connections.values()):
                try:
                    await conn.websocket.close(code=1001)
                except Exception:
                    pass
            self._connections.clear()
            self._user_connections.clear()

    async def send(self, conn_id: str, message: dict) -> bool:
        conn = self._connections.get(conn_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(message)
            return True
        except Exception as exc:
            logger.warning(f"Failed to send to {conn_id}: {exc}")
            await self.disconnect(conn_id)
            return False

    async def send_to_user(self, user_id: str, message: dict) -> int:
        conn_ids = list(self._user_connections.get(user_id, set()))
        results = await asyncio.gather(*[self.send(cid, message) for cid in conn_ids])
        return sum(results)

    async def broadcast(self, message: dict, exclude: Optional[str] = None) -> int:
        conn_ids = [cid for cid in self._connections if cid != exclude]
        results = await asyncio.gather(*[self.send(cid, message) for cid in conn_ids])
        return sum(results)

    def get_connection(self, conn_id: str) -> Optional[Connection]:
        return self._connections.get(conn_id)

    def get_user_connections(self, user_id: str) -> list:
        return [
            self._connections[cid]
            for cid in self._user_connections.get(user_id, set())
            if cid in self._connections
        ]

    @property
    def total_connections(self) -> int:
        return len(self._connections)

    @property
    def online_user_ids(self) -> list:
        return list(self._user_connections.keys())
