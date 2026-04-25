"""Redis client singleton + helpers."""
from typing import Any

import redis.asyncio as redis_lib

from app.config import settings

redis: redis_lib.Redis = redis_lib.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)


async def cache_get(key: str) -> str | None:
    return await redis.get(key)


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    await redis.set(key, value, ex=ttl)


async def cache_delete(*keys: str) -> None:
    if keys:
        await redis.delete(*keys)


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching pattern (use sparingly)."""
    async for key in redis.scan_iter(match=pattern, count=100):
        await redis.delete(key)


async def get_redis() -> redis_lib.Redis:
    """Return the shared async Redis client (ping verifies liveness)."""
    await redis.ping()
    return redis


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    await redis.aclose()
