import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class Channel:
    name: str
    persistent: bool = False
    max_members: Optional[int] = None
    private: bool = False
    members: Set[str] = field(default_factory=set)   # conn_ids
    metadata: Dict = field(default_factory=dict)

    @property
    def member_count(self) -> int:
        return len(self.members)

    def is_full(self) -> bool:
        return self.max_members is not None and self.member_count >= self.max_members


class ChannelRegistry:
    """
    Manages channel membership and pub/sub fan-out.
    """

    def __init__(self):
        self._channels: Dict[str, Channel] = {}
        self._lock = asyncio.Lock()

    async def load_persistent_channels(self):
        """Load pre-configured channels from DB/config on startup."""
        defaults = [
            Channel(name="general", persistent=True),
            Channel(name="announcements", persistent=True, private=False),
            Channel(name="support", persistent=True, max_members=500),
        ]
        async with self._lock:
            for ch in defaults:
                self._channels[ch.name] = ch
        logger.info(f"Loaded {len(defaults)} persistent channels")

    async def join(self, channel_name: str, conn_id: str) -> bool:
        async with self._lock:
            ch = self._channels.setdefault(channel_name, Channel(name=channel_name))
            if ch.is_full():
                logger.warning(f"Channel '{channel_name}' is full — rejecting {conn_id}")
                return False
            ch.members.add(conn_id)
            logger.debug(f"{conn_id} joined '{channel_name}' ({ch.member_count} members)")
            return True

    async def leave(self, channel_name: str, conn_id: str):
        async with self._lock:
            ch = self._channels.get(channel_name)
            if ch:
                ch.members.discard(conn_id)
                if not ch.persistent and ch.member_count == 0:
                    del self._channels[channel_name]
                    logger.debug(f"Channel '{channel_name}' destroyed (empty)")

    async def get_members(self, channel_name: str) -> Set[str]:
        ch = self._channels.get(channel_name)
        return set(ch.members) if ch else set()

    async def publish(self, channel_name: str, message: dict, manager, exclude: Optional[str] = None) -> int:
        members = await self.get_members(channel_name)
        targets = [cid for cid in members if cid != exclude]
        results = await asyncio.gather(*[manager.send(cid, message) for cid in targets])
        delivered = sum(results)
        logger.debug(f"Published to '{channel_name}': {delivered}/{len(targets)} delivered")
        return delivered

    async def list_channels(self) -> List[dict]:
        return [
            {
                "name": ch.name,
                "member_count": ch.member_count,
                "persistent": ch.persistent,
                "private": ch.private,
                "max_members": ch.max_members,
            }
            for ch in self._channels.values()
        ]

    def get_channel(self, name: str) -> Optional[Channel]:
        return self._channels.get(name)

    @property
    def total_channels(self) -> int:
        return len(self._channels)
