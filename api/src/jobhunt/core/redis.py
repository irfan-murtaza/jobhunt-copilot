"""Shared Redis client factory (cache, rate limiting, arq queue)."""

from __future__ import annotations

from redis.asyncio import Redis

from jobhunt.core.config import Settings, get_settings

_client: Redis | None = None


def get_redis(settings: Settings | None = None) -> Redis:
    global _client
    if _client is None:
        settings = settings or get_settings()
        _client = Redis.from_url(str(settings.redis_url), decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
