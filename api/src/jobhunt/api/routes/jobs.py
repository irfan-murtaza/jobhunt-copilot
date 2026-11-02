"""Job feed: browse ingested jobs, add one manually, trigger ingestion, inspect sources."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from jobhunt.ai.factory import model_for
from jobhunt.ai.provider import ModelRole
from jobhunt.api.deps import CurrentUser, EmbeddingsDep, LLMDep, SessionDep, SettingsDep
from jobhunt.core.ratelimit import limiter
from jobhunt.models import ExtractionStatus, Job, JobSource, SourceFetch
from jobhunt.schemas.common import Message
from jobhunt.schemas.job import (
    JobDetail,
    JobExtraction,
    JobList,
    JobRead,
    ManualJobCreate,
    SourceStatus,
)
from jobhunt.services.extraction import ExtractionService
from jobhunt.services.ingestion import IngestionService
from jobhunt.services.normalize import canonical_url, content_hash, normalize_company
from jobhunt.services.url_fetch import UnsafeURLError, fetch_page_text
from jobhunt.sources.base import RawJob
from jobhunt.sources.registry import build_sources
from jobhunt.worker.queue import enqueue

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_read(job: Job, *, detail: bool = False) -> JobRead:
    model = JobDetail if detail else JobRead
    data = {
        "id": job.id,
        "source": job.source,
        "url": job.url,
        "title": job.title,
        "company": job.company,
        "location_text": job.location_text,
        "salary_text": job.salary_text,
        "tags": job.tags or [],
        "posted_at": job.posted_at,
        "fetched_at": job.fetched_at,
        "extraction_status": job.extraction_status,
        "extraction": JobExtraction.model_validate(job.extraction) if job.extraction else None,
        "dedup_group_id": job.dedup_group_id,
        "is_duplicate": job.dedup_group_id is not None and job.dedup_group_id != job.id,
    }
    if detail:
        data |= {
            "description": job.description,
            "extraction_model": job.extraction_model,
            "extraction_cost_usd": job.extraction_cost_usd,
            "extraction_latency_ms": job.extraction_latency_ms,
        }
    return model.model_validate(data)


@router.get("", response_model=JobList)
async def list_jobs(
    _: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200, description="Search title and company")] = None,
    source: Annotated[JobSource | None, Query()] = None,
    extracted_only: bool = False,
    include_duplicates: bool = False,
    since: Annotated[datetime | None, Query(description="Posted or fetched after")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobList:
    stmt = select(Job).where(Job.is_active.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(pattern), Job.company.ilike(pattern)))
    if source:
        stmt = stmt.where(Job.source == source)
    if extracted_only:
        stmt = stmt.where(Job.extraction_status == ExtractionStatus.DONE)
    if not include_duplicates:
        stmt = stmt.where(or_(Job.dedup_group_id.is_(None), Job.dedup_group_id == Job.id))
    if since:
        stmt = stmt.where(func.coalesce(Job.posted_at, Job.fetched_at) >= since)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(func.coalesce(Job.posted_at, Job.fetched_at).desc())
        .limit(limit)
        .offset(offset)
    )
    return JobList(items=[_to_read(j) for j in rows], total=total, limit=limit, offset=offset)


@router.get("/sources", response_model=list[SourceStatus])
async def list_sources(
    _: CurrentUser, session: SessionDep, settings: SettingsDep
) -> list[SourceStatus]:
    statuses: list[SourceStatus] = []
    for source in build_sources(settings):
        last = await session.scalar(
            select(SourceFetch)
            .where(SourceFetch.source.like(f"{source.name}%"))
            .order_by(SourceFetch.fetched_at.desc())
            .limit(1)
        )
        statuses.append(
            SourceStatus(
                name=str(source.name),
                attribution=source.attribution,
                last_fetched_at=last.fetched_at if last else None,
                last_status_code=last.status_code if last else None,
                last_items_seen=last.items_seen if last else None,
                last_items_new=last.items_new if last else None,
                last_error=last.error if last else None,
            )
        )
    return statuses


@router.post("/ingest", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def trigger_ingestion(request: Request, _: CurrentUser) -> Message:
    """Queue a fetch from every source followed by extraction of pending jobs."""
    job = await enqueue("ingest_all")
    return Message(detail=f"Ingestion queued ({job})")


@router.post("/manual", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_manual_job(
    request: Request,
    body: ManualJobCreate,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    llm: LLMDep,
    embeddings: EmbeddingsDep,
) -> JobDetail:
    """Paste a job URL or description. It is fetched if needed, stored and extracted immediately."""
    description = (body.description or "").strip()
    if not description and body.url:
        try:
            description = await fetch_page_text(body.url)
        except UnsafeURLError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Could not fetch URL: {exc}"
            ) from exc
    if len(description) < 50:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide a job URL or a description"
        )

    source_id = uuid.uuid4().hex
    raw = RawJob(
        source=JobSource.MANUAL,
        source_id=source_id,
        url=body.url or f"manual://{source_id}",
        title=body.title or "Untitled (pending extraction)",
        company=body.company or "Unknown",
        description=description,
        posted_at=datetime.now(UTC),
    )
    # Manual jobs never go through the shared HTTP client, so pass a bare one.
    from jobhunt.sources.http import SourceHttpClient

    ingestion = IngestionService(session, SourceHttpClient())
    await ingestion.upsert(raw)
    job = await session.scalar(
        select(Job).where(Job.source == JobSource.MANUAL, Job.source_id == source_id)
    )
    assert job is not None
    job.created_by_user_id = user.id

    extractor = ExtractionService(
        session, llm, embeddings, model=model_for(ModelRole.EXTRACT, settings)
    )
    outcome = await extractor.extract(job)
    if outcome.status == ExtractionStatus.DONE and job.extraction:
        extraction = JobExtraction.model_validate(job.extraction)
        if not body.title:
            job.title = extraction.title[:300]
        if not body.company and extraction.company:
            job.company = extraction.company[:200]
            job.company_normalized = normalize_company(job.company)
        job.content_hash = content_hash(job.title, job.company, job.description)
        if body.url:
            job.canonical_url = canonical_url(body.url)
    await session.flush()
    return _to_read(job, detail=True)  # type: ignore[return-value]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: uuid.UUID, _: CurrentUser, session: SessionDep) -> JobDetail:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return _to_read(job, detail=True)  # type: ignore[return-value]
