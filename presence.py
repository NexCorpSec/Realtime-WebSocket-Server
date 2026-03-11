import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30   # seconds
IDLE_THRESHOLD     = 120  # seconds before marking idle
OFFLINE_THRESHOLD  = 300  # seconds before marking offline


@dataclass
class UserPresence:
    user_id: str
    status: str = "online"       # online | idle | offline
    last_seen: float = field(default_factory=time.time)
    connections: Dict[str, str] = field(default_factory=dict)   # conn_id → channel
    custom_status: Optional[str] = None


class PresenceTracker:
    def __init__(self):
        self._users: Dict[str, UserPresence] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start_heartbeat_loop(self):
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

    async def mark_online(self, user_id: str, conn_id: str, channel: str):
        async with self._lock:
            p = self._users.setdefault(user_id, UserPresence(user_id=user_id))
            p.connections[conn_id] = channel
            p.status = "online"
            p.last_seen = time.time()

    async def mark_offline(self, user_id: str, conn_id: str):
        async with self._lock:
            p = self._users.get(user_id)
            if not p:
                return
            p.connections.pop(conn_id, None)
            if not p.connections:
                p.status = "offline"
                p.last_seen = time.time()

    async def update_status(self, user_id: str, status: str, custom_status: Optional[str] = None):
        allowed = {"online", "idle", "dnd"}
        if status not in allowed:
            return False
        async with self._lock:
            p = self._users.get(user_id)
            if p:
                p.status = status
                p.custom_status = custom_status
                p.last_seen = time.time()
        return True

    async def heartbeat(self, user_id: str, conn_id: str):
        async with self._lock:
            p = self._users.get(user_id)
            if p and conn_id in p.connections:
                p.last_seen = time.time()
                if p.status == "idle":
                    p.status = "online"

    def get_presence(self, user_id: str) -> Optional[dict]:
        p = self._users.get(user_id)
        if not p:
            return None
        return {
            "user_id": p.user_id,
            "status": p.status,
            "last_seen": p.last_seen,
            "custom_status": p.custom_status,
            "connection_count": len(p.connections),
        }

    def get_online_users(self) -> list:
        return [
            self.get_presence(uid)
            for uid, p in self._users.items()
            if p.status != "offline"
        ]

    async def _heartbeat(self):
        """Periodically sweep for idle / timed-out users."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            async with self._lock:
                for p in self._users.values():
                    if p.status == "offline":
                        continue
                    elapsed = now - p.last_seen
                    if elapsed > OFFLINE_THRESHOLD and not p.connections:
                        p.status = "offline"
                    elif elapsed > IDLE_THRESHOLD and p.status == "online":
                        p.status = "idle"
            logger.debug("Presence sweep complete")
