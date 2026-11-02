"""Two-stage deduplication.

Stage 1 (at ingest, exact): same canonical URL, or same content hash, or same normalised
company and title posted within a month. Cheap, runs for every job.

Stage 2 (after extraction, fuzzy): same normalised company and embedding cosine similarity
above a threshold. Catches reworded reposts across boards.

Every job carries `dedup_group_id`: the id of the first job we saw in its group. A job
whose group id equals its own id is the canonical copy; the others are duplicates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.core.logging import get_logger
from jobhunt.models import Job
from jobhunt.services.normalize import normalize_title

log = get_logger(__name__)

NEAR_DUPLICATE_THRESHOLD = 0.95
RECENT_WINDOW = timedelta(days=30)


async def assign_exact_duplicate_group(session: AsyncSession, job: Job) -> bool:
    """Set job.dedup_group_id. Returns True when the job duplicates an existing one."""
    candidates = await session.scalars(
        select(Job)
        .where(Job.id != job.id, Job.company_normalized == job.company_normalized)
        .order_by(Job.fetched_at)
    )
    recent_cutoff = (job.posted_at or job.fetched_at or datetime.now(UTC)) - RECENT_WINDOW
    title_key = normalize_title(job.title)
    for other in candidates:
        same_url = bool(job.canonical_url) and other.canonical_url == job.canonical_url
        same_hash = other.content_hash == job.content_hash
        same_title_recent = (
            normalize_title(other.title) == title_key
            and (other.posted_at or other.fetched_at) >= recent_cutoff
        )
        if same_url or same_hash or same_title_recent:
            job.dedup_group_id = other.dedup_group_id or other.id
            log.info(
                "dedup.exact",
                job_id=str(job.id),
                group=str(job.dedup_group_id),
                reason="url" if same_url else "hash" if same_hash else "title",
            )
            return True
    job.dedup_group_id = job.id
    return False


async def assign_near_duplicate_group(session: AsyncSession, job: Job) -> bool:
    """Fuzzy stage. Requires job.embedding. Returns True if re-grouped under an older job."""
    if job.embedding is None or job.dedup_group_id != job.id:
        return False
    distance = Job.embedding.cosine_distance(job.embedding)
    nearest = (
        await session.execute(
            select(Job, distance.label("distance"))
            .where(
                Job.id != job.id,
                Job.company_normalized == job.company_normalized,
                Job.embedding.is_not(None),
                Job.fetched_at <= job.fetched_at,
            )
            .order_by(distance)
            .limit(1)
        )
    ).first()
    if nearest is None:
        return False
    other, dist = nearest
    log.debug(
        "dedup.near_candidate",
        job_id=str(job.id),
        other=str(other.id),
        similarity=round(1 - dist, 4),
    )
    if 1 - dist >= NEAR_DUPLICATE_THRESHOLD:
        job.dedup_group_id = other.dedup_group_id or other.id
        log.info(
            "dedup.near",
            job_id=str(job.id),
            group=str(job.dedup_group_id),
            similarity=round(1 - dist, 4),
        )
        return True
    return False
