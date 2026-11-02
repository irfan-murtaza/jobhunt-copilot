"""Structured extraction of job postings with the cheap model, plus job embeddings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.ai.provider import EmbeddingProvider, LLMError, LLMProvider
from jobhunt.core.logging import get_logger
from jobhunt.models import ExtractionStatus, Job
from jobhunt.schemas.job import JobExtraction
from jobhunt.services.dedup import assign_near_duplicate_group

log = get_logger(__name__)

MAX_DESCRIPTION_CHARS = 20_000

JOB_EXTRACTION_SYSTEM = """You extract structured hiring requirements from a job posting.

Rules:
- Report only what the posting states. Use "unspecified" or null when it does not say.
- must_have_skills are explicitly required: "required", "must have", "you have", "X+ years
  of". nice_to_have_skills are "bonus", "nice to have", "preferred", "familiarity with".
  Name concrete technologies and tools, not soft skills.
- location: if candidates may live anywhere, scope = worldwide. If specific countries are
  named, scope = countries with ISO alpha-2 codes. If a region is named (Europe, EMEA,
  Americas, LATAM, APAC, "US time zones"), scope = regions. If only a timezone band is
  given, scope = timezone with UTC offsets. Record excluded countries separately. Quote the
  statement in `text`.
- remote: fully_remote only when the role is remote with no office attendance required.
- salary: numbers as written, with currency and period; do not convert or estimate.
- seniority from the title or stated level; years_experience_min from an explicit minimum.
- confidence is low for terse or informal posts (e.g. forum comments), high for complete
  postings with an explicit requirements section."""


@dataclass(slots=True)
class ExtractionOutcome:
    job_id: str
    status: ExtractionStatus
    cost_usd: float | None = None
    latency_ms: int | None = None
    error: str | None = None
    near_duplicate: bool = False


def build_extraction_prompt(job: Job) -> str:
    header = [f"Title: {job.title}", f"Company: {job.company}", f"Source: {job.source}"]
    if job.location_text:
        header.append(f"Location (as listed): {job.location_text}")
    if job.salary_text:
        header.append(f"Salary (as listed): {job.salary_text}")
    if job.tags:
        header.append(f"Tags: {', '.join(job.tags)}")
    description = job.description[:MAX_DESCRIPTION_CHARS]
    return "\n".join(header) + f"\n\n<posting>\n{description}\n</posting>"


def embedding_text_for_job(job: Job, extraction: JobExtraction | None) -> str:
    parts = [job.title, job.company]
    if extraction:
        parts.append(extraction.summary)
        parts.append("Required: " + ", ".join(extraction.must_have_skills))
        if extraction.nice_to_have_skills:
            parts.append("Nice to have: " + ", ".join(extraction.nice_to_have_skills))
    parts.append(job.description[:4000])
    return "\n".join(p for p in parts if p)


class ExtractionService:
    def __init__(
        self, session: AsyncSession, llm: LLMProvider, embeddings: EmbeddingProvider, *, model: str
    ) -> None:
        self._session = session
        self._llm = llm
        self._embeddings = embeddings
        self._model = model

    async def pending_job_ids(self, limit: int) -> list[str]:
        rows = await self._session.scalars(
            select(Job.id)
            .where(Job.extraction_status == ExtractionStatus.PENDING, Job.is_active.is_(True))
            .order_by(Job.fetched_at.desc())
            .limit(limit)
        )
        return [str(r) for r in rows]

    async def extract(self, job: Job) -> ExtractionOutcome:
        try:
            result = await self._llm.complete_structured(
                model=self._model,
                schema=JobExtraction,
                system=JOB_EXTRACTION_SYSTEM,
                prompt=build_extraction_prompt(job),
                max_tokens=2000,
                effort="low",
            )
        except LLMError as exc:
            job.extraction_status = ExtractionStatus.FAILED
            job.extraction_error = str(exc)[:1000]
            await self._session.flush()
            log.warning("extract.failed", job_id=str(job.id), error=str(exc))
            return ExtractionOutcome(str(job.id), ExtractionStatus.FAILED, error=str(exc))

        extraction = result.output
        job.extraction = extraction.model_dump(mode="json")
        job.extraction_status = ExtractionStatus.DONE
        job.extraction_error = None
        job.extraction_model = result.model
        job.extraction_cost_usd = result.cost_usd
        job.extraction_latency_ms = result.latency_ms

        [vector] = await self._embeddings.embed([embedding_text_for_job(job, extraction)])
        job.embedding = vector
        await self._session.flush()
        near = await assign_near_duplicate_group(self._session, job)
        await self._session.flush()
        log.info(
            "extract.done",
            job_id=str(job.id),
            model=result.model,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            must_have=len(extraction.must_have_skills),
            scope=extraction.location.scope,
        )
        return ExtractionOutcome(
            str(job.id),
            ExtractionStatus.DONE,
            result.cost_usd,
            result.latency_ms,
            near_duplicate=near,
        )
