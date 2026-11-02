"""Pipeline tests against real Postgres: upsert, change detection, dedup, extraction."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.ai.embeddings import HashEmbeddingProvider
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.models import ExtractionStatus, Job, JobSource, SourceFetch
from jobhunt.schemas.job import JobExtraction, LocationEligibility, LocationScope, Seniority
from jobhunt.services.extraction import ExtractionService
from jobhunt.services.ingestion import IngestionService
from jobhunt.sources.base import RawJob, SourceError
from jobhunt.sources.http import SourceHttpClient

pytestmark = pytest.mark.db

DESCRIPTION = (
    "We are hiring a Senior Backend Engineer. 5+ years Python. PostgreSQL. Remote anywhere."
)
LONG_DESCRIPTION = " ".join(
    f"Requirement {i}: Python, PostgreSQL, Kafka, Docker, AWS, Terraform, observability."
    for i in range(12)
)


def raw(
    source: JobSource = JobSource.REMOTIVE, source_id: str = "1", **overrides: object
) -> RawJob:
    base: dict[str, object] = {
        "source": source,
        "source_id": source_id,
        "url": f"https://{source}.test/jobs/{source_id}",
        "title": "Senior Backend Engineer",
        "company": "Acme Robotics Inc.",
        "description": DESCRIPTION,
        "posted_at": datetime(2026, 10, 30, tzinfo=UTC),
    }
    base.update(overrides)
    return RawJob(**base)  # type: ignore[arg-type]


class StaticSource:
    name = JobSource.REMOTIVE
    attribution = "test"
    cooldown_seconds = 0
    cache_ttl_seconds = 0

    def __init__(self, jobs: list[RawJob] | Exception) -> None:
        self._jobs = jobs

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        if isinstance(self._jobs, Exception):
            raise self._jobs
        return self._jobs


async def test_upsert_is_idempotent_and_detects_content_changes(session: AsyncSession) -> None:
    service = IngestionService(session, SourceHttpClient())
    assert await service.upsert(raw()) == "new"
    assert await service.upsert(raw()) == "unchanged"
    assert await service.upsert(raw(description=DESCRIPTION + " Now with Kafka.")) == "updated"
    job = await session.scalar(select(Job).where(Job.source_id == "1"))
    assert job is not None
    assert job.extraction_status == ExtractionStatus.PENDING and "Kafka" in job.description
    assert await session.scalar(select(func.count()).select_from(Job)) == 1


async def test_cross_board_repost_is_grouped_as_duplicate(session: AsyncSession) -> None:
    service = IngestionService(session, SourceHttpClient())
    await service.upsert(raw(JobSource.REMOTIVE, "1"))
    assert (
        await service.upsert(
            raw(
                JobSource.REMOTEOK,
                "7001",
                title="Senior Backend Engineer (Remote)",
                company="Acme Robotics",
            )
        )
        == "duplicate"
    )
    assert (
        await service.upsert(
            raw(
                JobSource.REMOTEOK,
                "7002",
                title="Frontend Developer",
                company="Acme Robotics",
                description="React. " * 10,
            )
        )
        == "new"
    )

    jobs = {j.source_id: j for j in await session.scalars(select(Job))}
    assert jobs["7001"].dedup_group_id == jobs["1"].id  # duplicate points at the canonical copy
    assert jobs["1"].dedup_group_id == jobs["1"].id
    assert jobs["7002"].dedup_group_id == jobs["7002"].id


async def test_run_isolates_source_failures_and_logs_fetches(session: AsyncSession) -> None:
    service = IngestionService(session, SourceHttpClient())
    good = StaticSource(
        [raw(source_id="1"), raw(source_id="2", title="Data Engineer", description="Spark. " * 10)]
    )
    bad = StaticSource(SourceError("upstream exploded"))
    bad.name = JobSource.REMOTEOK  # type: ignore[misc]
    report = await service.run([good, bad])
    assert report.new == 2 and report.fetched == 2
    assert report.errors == {"remoteok": "SourceError: upstream exploded"}
    fetches = list(await session.scalars(select(SourceFetch).order_by(SourceFetch.source)))
    assert [(f.source, f.items_new, bool(f.error)) for f in fetches] == [
        ("remoteok", 0, True),
        ("remotive", 2, False),
    ]


async def test_extraction_stores_structure_cost_and_embedding(session: AsyncSession) -> None:
    ingestion = IngestionService(session, SourceHttpClient())
    await ingestion.upsert(raw())
    job = await session.scalar(select(Job))
    assert job is not None

    fake = FakeLLMProvider()
    fake.respond_with(
        JobExtraction(
            title="Senior Backend Engineer",
            seniority=Seniority.SENIOR,
            years_experience_min=5,
            must_have_skills=["Python", "PostgreSQL", "python"],
            location=LocationEligibility(scope=LocationScope.WORLDWIDE, text="Remote anywhere"),
            summary="Backend role on a robotics platform.",
        ),
        schema=JobExtraction,
    )
    service = ExtractionService(session, fake, HashEmbeddingProvider(), model="cheap-model")
    assert await service.pending_job_ids(10) == [str(job.id)]
    outcome = await service.extract(job)

    assert outcome.status == ExtractionStatus.DONE and outcome.error is None
    assert job.extraction_status == ExtractionStatus.DONE
    assert job.extraction is not None and job.extraction["must_have_skills"] == [
        "Python",
        "PostgreSQL",
    ]
    assert job.extraction_model == "cheap-model" and job.extraction_cost_usd == 0.0
    assert job.embedding is not None and len(job.embedding) == 1536
    assert "<posting>" in fake.calls[0].prompt and "Acme Robotics" in fake.calls[0].prompt
    assert await service.pending_job_ids(10) == []


async def test_extraction_failure_is_recorded_not_raised(session: AsyncSession) -> None:
    from jobhunt.ai.provider import LLMError

    await IngestionService(session, SourceHttpClient()).upsert(raw())
    job = await session.scalar(select(Job))
    assert job is not None

    class Failing(FakeLLMProvider):
        async def complete_structured(self, **kwargs):  # type: ignore[no-untyped-def,override]
            raise LLMError("boom")

    outcome = await ExtractionService(
        session, Failing(), HashEmbeddingProvider(), model="m"
    ).extract(job)
    assert outcome.status == ExtractionStatus.FAILED and outcome.error == "boom"
    assert job.extraction_status == ExtractionStatus.FAILED and job.extraction_error == "boom"


async def test_near_duplicate_detected_by_embedding(session: AsyncSession) -> None:
    ingestion = IngestionService(session, SourceHttpClient())
    await ingestion.upsert(raw(JobSource.REMOTIVE, "1", description=LONG_DESCRIPTION))
    # Different title and wording so exact dedup misses it, but near-identical content.
    await ingestion.upsert(
        raw(
            JobSource.WEWORKREMOTELY,
            "x",
            title="Backend Engineer, Senior",
            company="Acme Robotics",
            description=LONG_DESCRIPTION + " Apply today.",
        )
    )
    jobs = {j.source_id: j for j in await session.scalars(select(Job))}
    assert jobs["x"].dedup_group_id == jobs["x"].id

    fake = FakeLLMProvider()
    fake.respond_with(
        JobExtraction(title="Senior Backend Engineer", summary="Backend role."),
        schema=JobExtraction,
    )
    service = ExtractionService(session, fake, HashEmbeddingProvider(), model="m")
    await service.extract(jobs["1"])
    outcome = await service.extract(jobs["x"])
    assert outcome.near_duplicate is True
    assert jobs["x"].dedup_group_id == jobs["1"].id
