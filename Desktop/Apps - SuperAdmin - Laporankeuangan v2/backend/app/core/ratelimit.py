"""Sliding-window rate limiting using Redis."""
import time

from app.core.cache import redis
from app.core.exceptions import RateLimitError


async def check_rate_limit(key: str, limit: int, window_sec: int = 60) -> None:
    """Increment counter for current window; raise if over limit.

    Args:
        key: Unique identifier (e.g., "user:<id>", "ip:<addr>")
        limit: Max requests in window
        window_sec: Window size in seconds
    """
    bucket = f"rl:{key}:{int(time.time() // window_sec)}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(bucket)
        pipe.expire(bucket, window_sec)
        results = await pipe.execute()
    count = results[0]
    if count > limit:
        raise RateLimitError(
            f"Rate limit exceeded ({limit}/{window_sec}s)",
            details={"limit": limit, "window": window_sec, "current": count},
        )
