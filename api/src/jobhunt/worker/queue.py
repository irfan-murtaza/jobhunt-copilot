"""Enqueue helpers used by the API to hand work to the arq worker."""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis

from jobhunt.worker.settings import redis_settings

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue(function: str, *args: Any, **kwargs: Any) -> str:
    pool = await get_pool()
    job = await pool.enqueue_job(function, *args, **kwargs)
    return job.job_id if job else "already-queued"


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None
