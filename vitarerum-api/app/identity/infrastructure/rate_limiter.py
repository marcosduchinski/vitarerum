"""In-memory sliding-window rate limiter.

Sufficient for a single application instance. A multi-instance deployment must
replace this with a shared store (e.g. Redis) so limits hold across replicas.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class InMemorySlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.monotonic()
        hits = self._buckets[key]
        cutoff = now - window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= max_requests:
            return True
        hits.append(now)
        return False
