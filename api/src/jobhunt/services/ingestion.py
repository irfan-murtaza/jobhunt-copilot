"""Fetch from every source, normalise, upsert and record what happened.

One source failing must never stop the others, and re-running must be idempotent: a job
is identified by (source, source_id); its content hash tells us whether it changed.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.core.logging import get_logger
from jobhunt.models import ExtractionStatus, Job, SourceFetch
from jobhunt.services.dedup import assign_exact_duplicate_group
from jobhunt.services.normalize import canonical_url, content_hash, normalize_company
from jobhunt.sources.base import JobBoardSource, RawJob, SourceError
from jobhunt.sources.http import CooldownActiveError, SourceHttpClient

log = get_logger(__name__)


@dataclass(slots=True)
class SourceReport:
    seen: int = 0
    new: int = 0
    updated: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str | None = None
    from_cache: bool = False


@dataclass(slots=True)
class IngestionReport:
    sources: dict[str, SourceReport] = field(default_factory=dict)

    @property
    def fetched(self) -> int:
        return sum(r.seen for r in self.sources.values())

    @property
    def new(self) -> int:
        return sum(r.new for r in self.sources.values())

    @property
    def updated(self) -> int:
        return sum(r.updated for r in self.sources.values())

    @property
    def duplicates(self) -> int:
        return sum(r.duplicates for r in self.sources.values())

    @property
    def errors(self) -> dict[str, str]:
        return {name: r.error for name, r in self.sources.items() if r.error}

    def as_dict(self) -> dict[str, object]:
        return {
            "sources": {k: asdict(v) for k, v in self.sources.items()},
            "fetched": self.fetched,
            "new": self.new,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "errors": self.errors,
        }


class IngestionService:
    def __init__(self, session: AsyncSession, http: SourceHttpClient) -> None:
        self._session = session
        self._http = http

    async def run(self, sources: list[JobBoardSource]) -> IngestionReport:
        report = IngestionReport()
        for source in sources:
            report.sources[str(source.name)] = await self.run_source(source)
        log.info("ingest.done", **{k: v for k, v in report.as_dict().items() if k != "sources"})
        return report

    async def run_source(self, source: JobBoardSource) -> SourceReport:
        started = time.perf_counter()
        report = SourceReport()
        fetch_log = SourceFetch(
            source=str(source.name), url=str(source.name), fetched_at=datetime.now(UTC)
        )
        try:
            raw_jobs = await source.fetch(self._http)
        except CooldownActiveError as exc:
            report.error = str(exc)
            report.skipped = 1
            log.info("ingest.cooldown", source=str(source.name), retry_in=exc.retry_in)
            return report
        except (SourceError, httpx.HTTPError, ValueError, KeyError) as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            fetch_log.error = report.error
            log.warning("ingest.source_failed", source=str(source.name), error=report.error)
            self._session.add(fetch_log)
            await self._session.flush()
            return report

        for raw in raw_jobs:
            outcome = await self.upsert(raw)
            report.seen += 1
            if outcome == "new":
                report.new += 1
            elif outcome == "updated":
                report.updated += 1
            elif outcome == "duplicate":
                report.duplicates += 1
                report.new += 1  # it is still a new row; flagged as a repost of an existing one

        fetch_log.status_code = 200
        fetch_log.items_seen = report.seen
        fetch_log.items_new = report.new
        fetch_log.duration_ms = int((time.perf_counter() - started) * 1000)
        self._session.add(fetch_log)
        await self._session.flush()
        log.info(
            "ingest.source_done",
            source=str(source.name),
            **{k: v for k, v in asdict(report).items() if k != "error"},
        )
        return report

    async def upsert(self, raw: RawJob) -> str:
        """Insert or refresh one job. Returns new | updated | unchanged | duplicate."""
        title = raw.title.strip()[:300] or "Untitled"
        company = raw.company.strip()[:200] or "Unknown"
        description = raw.description.strip()
        digest = content_hash(title, company, description)

        existing = await self._session.scalar(
            select(Job).where(Job.source == raw.source, Job.source_id == raw.source_id)
        )
        if existing is not None:
            existing.is_active = True
            if existing.content_hash == digest:
                return "unchanged"
            existing.title = title
            existing.company = company
            existing.company_normalized = normalize_company(company)
            existing.description = description
            existing.location_text = raw.location_text
            existing.salary_text = raw.salary_text
            existing.tags = raw.tags[:30]
            existing.content_hash = digest
            existing.fetched_at = datetime.now(UTC)
            existing.extraction_status = ExtractionStatus.PENDING
            existing.extraction_error = None
            await self._session.flush()
            return "updated"

        job = Job(
            source=raw.source,
            source_id=raw.source_id,
            url=raw.url,
            canonical_url=canonical_url(raw.url),
            title=title,
            company=company,
            company_normalized=normalize_company(company),
            location_text=raw.location_text,
            salary_text=raw.salary_text,
            tags=raw.tags[:30],
            description=description,
            content_hash=digest,
            posted_at=raw.posted_at,
            fetched_at=datetime.now(UTC),
        )
        self._session.add(job)
        await self._session.flush()
        is_duplicate = await assign_exact_duplicate_group(self._session, job)
        return "duplicate" if is_duplicate else "new"
