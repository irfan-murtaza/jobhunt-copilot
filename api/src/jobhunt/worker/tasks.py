"""Background tasks. Each task opens its own DB session and commits per unit of work, so a
crash half-way loses at most one job's progress."""

from __future__ import annotations

from typing import Any

from jobhunt.ai.factory import get_embedding_provider, get_llm_provider, model_for
from jobhunt.ai.provider import ModelRole
from jobhunt.core.config import get_settings
from jobhunt.core.db import get_sessionmaker
from jobhunt.core.logging import get_logger
from jobhunt.core.redis import get_redis
from jobhunt.models import Job
from jobhunt.services.extraction import ExtractionService
from jobhunt.services.ingestion import IngestionService
from jobhunt.sources.http import SourceHttpClient
from jobhunt.sources.registry import build_sources

log = get_logger(__name__)


async def ingest_all(ctx: dict[str, Any], *, extract: bool = True) -> dict[str, Any]:
    settings = get_settings()
    http = SourceHttpClient(redis=get_redis(settings))
    try:
        async with get_sessionmaker()() as session:
            report = await IngestionService(session, http).run(build_sources(settings))
            await session.commit()
    finally:
        await http.aclose()
    if extract:
        await ctx["redis"].enqueue_job("extract_pending")
    return report.as_dict()


async def extract_pending(ctx: dict[str, Any], *, limit: int = 200) -> dict[str, Any]:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        service = ExtractionService(
            session,
            get_llm_provider(),
            get_embedding_provider(),
            model=model_for(ModelRole.EXTRACT, settings),
        )
        ids = await service.pending_job_ids(limit)
    for job_id in ids:
        await ctx["redis"].enqueue_job("extract_job", job_id, _job_id=f"extract:{job_id}")
    log.info("extract.queued", count=len(ids))
    return {"queued": len(ids)}


async def extract_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        service = ExtractionService(
            session,
            get_llm_provider(),
            get_embedding_provider(),
            model=model_for(ModelRole.EXTRACT, settings),
        )
        outcome = await service.extract(job)
        await session.commit()
    return {
        "job_id": job_id,
        "status": str(outcome.status),
        "cost_usd": outcome.cost_usd,
        "error": outcome.error,
    }
