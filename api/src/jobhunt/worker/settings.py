"""arq worker configuration.

Tasks are registered here; the worker process is `arq jobhunt.worker.settings.WorkerSettings`.
Cron jobs are added in the daily-agent milestone.
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from jobhunt.core.config import get_settings
from jobhunt.core.logging import configure_logging, get_logger

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    ctx["settings"] = settings
    log.info("worker.start", env=settings.app_env)


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stop")


async def ping(ctx: dict[str, Any], message: str = "pong") -> str:
    """Smoke-test task used by health checks and tests."""
    return message


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(str(get_settings().redis_url))


class WorkerSettings:
    functions = [ping]
    cron_jobs: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = 600
    max_tries = 3
    retry_jobs = True
    health_check_interval = 60
