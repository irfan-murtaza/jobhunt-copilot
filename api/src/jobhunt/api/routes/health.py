from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from jobhunt import __version__
from jobhunt.api.deps import SessionDep
from jobhunt.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready(session: SessionDep) -> dict[str, str]:
    """Readiness: dependencies answer."""
    await session.execute(text("SELECT 1"))
    await get_redis().ping()
    return {"status": "ready"}
