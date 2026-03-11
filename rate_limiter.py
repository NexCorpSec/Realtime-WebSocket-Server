import time
import asyncio
from collections import defaultdict
from typing import Dict


class WsRateLimiter:
    """Sliding-window rate limiter per connection."""

    def __init__(self, max_messages: int = 60, window_seconds: int = 10):
        self.max_messages = max_messages
        self.window = window_seconds
        self._buckets: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def allow(self, conn_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        async with self._lock:
            timestamps = self._buckets[conn_id]
            # Evict old entries
            self._buckets[conn_id] = [t for t in timestamps if t > cutoff]
            if len(self._buckets[conn_id]) >= self.max_messages:
                return False
            self._buckets[conn_id].append(now)
            return True

    async def clear(self, conn_id: str):
        async with self._lock:
            self._buckets.pop(conn_id, None)
