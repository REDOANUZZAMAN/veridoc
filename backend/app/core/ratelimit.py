"""Fixed-window rate limiter.

Uses Redis when reachable so limits hold across API replicas, and transparently
falls back to a per-process window when Redis is down (fail-open on the store,
never fail-open on the limit itself).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.core.config import settings
from app.core.errors import RateLimited
from app.core.logging import get_logger

logger = get_logger(__name__)

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_rate(spec: str) -> tuple[int, int]:
    """'300/minute' -> (300, 60)"""
    count, _, unit = spec.partition("/")
    return int(count), _UNITS.get(unit.strip().rstrip("s"), 60)


class _MemoryBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def incr(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            bucket = [t for t in self._hits[key] if now - t < window]
            bucket.append(now)
            self._hits[key] = bucket
            return len(bucket)


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryBackend()
        self._redis = None
        self._redis_checked = False

    def _get_redis(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.25)
            client.ping()
            self._redis = client
        except Exception:
            logger.warning("ratelimit_redis_unavailable_using_memory")
            self._redis = None
        return self._redis

    def check(self, key: str, spec: str) -> None:
        limit, window = parse_rate(spec)
        client = self._get_redis()
        if client is not None:
            try:
                bucket = f"rl:{key}:{int(time.time() // window)}"
                pipe = client.pipeline()
                pipe.incr(bucket, 1)
                pipe.expire(bucket, window + 1)
                hits = int(pipe.execute()[0])
            except Exception:
                self._redis = None
                hits = self._memory.incr(key, window)
        else:
            hits = self._memory.incr(key, window)
        if hits > limit:
            raise RateLimited(
                f"Rate limit exceeded ({limit} requests / {window}s). Retry shortly.",
                details={"limit": limit, "window_seconds": window},
            )


limiter = RateLimiter()
