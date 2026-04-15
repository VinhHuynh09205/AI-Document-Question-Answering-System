import time
from collections import defaultdict, deque
from threading import Lock

from app.services.interfaces.rate_limiter import IRateLimiter


class InMemoryRateLimiter(IRateLimiter):
    def __init__(self, limits: dict[str, int], window_seconds: int) -> None:
        self._limits = limits
        self._window_seconds = max(1, window_seconds)
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def consume(self, bucket: str, key: str) -> tuple[bool, int]:
        limit = self._limits.get(bucket)
        if limit is None or limit <= 0:
            return True, 0

        now = time.time()
        bucket_key = (bucket, key)

        with self._lock:
            queue = self._events[bucket_key]
            cutoff = now - self._window_seconds

            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit:
                retry_after = max(1, int(queue[0] + self._window_seconds - now))
                return False, retry_after

            queue.append(now)
            return True, 0
