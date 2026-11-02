"""Scoring pipeline against real Postgres with hash embeddings and a scripted judge."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helpers import load_sample
from jobhunt.ai.embeddings import HashEmbeddingProvider
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.models import ExtractionStatus, Job, JobScore, JobSource, Preferences, User
from jobhunt.schemas.job import JobExtraction, LocationEligibility, LocationScope, Seniority
from jobhunt.schemas.scoring import EvidenceMatch, FitJudgement, Recommendation
from jobhunt.services.extraction import embedding_text_for_job
from jobhunt.services.profile import ProfileService
from jobhunt.services.scoring import ScoringService, combine
from jobhunt.services.skills import SkillCoverage

pytestmark = pytest.mark.db


async def make_user(
    session: AsyncSession, email: str = "casey@example.com", **prefs: object
) -> User:
    user = User(email=email, password_hash="x")
    user.preferences = Preferences(
        seniority_levels=[], excluded_keywords=[], required_keywords=[], **prefs
    )  # type: ignore[arg-type]
    session.add(user)
    await session.flush()
    await ProfileService(session, HashEmbeddingProvider()).save(user, load_sample())
    return user


async def make_job(
    session: AsyncSession, title: str, description: str, extraction: JobExtraction, source_id: str
) -> Job:
    job = Job(
        source=JobSource.REMOTIVE,
        source_id=source_id,
        url=f"https://x.test/{source_id}",
        title=title,
        company="Acme",
        company_normalized="acme",
        description=description,
        content_hash=source_id,
        fetched_at=datetime.now(UTC),
        extraction=extraction.model_dump(mode="json"),
        extraction_status=ExtractionStatus.DONE,
    )
    job.dedup_group_id = None
    session.add(job)
    await session.flush()
    job.dedup_group_id = job.id
    [job.embedding] = await HashEmbeddingProvider().embed([embedding_text_for_job(job, extraction)])
    await session.flush()
    return job


BACKEND = JobExtraction(
    title="Senior Backend Engineer",
    summary="Python services on Postgres and Kafka.",
    seniority=Seniority.SENIOR,
    must_have_skills=["Python", "PostgreSQL", "Kafka"],
    location=LocationEligibility(scope=LocationScope.WORLDWIDE),
)
SALES = JobExtraction(
    title="Account Executive",
    summary="Enterprise sales.",
    must_have_skills=["Salesforce", "Cold calling", "Negotiation"],
    location=LocationEligibility(scope=LocationScope.WORLDWIDE),
)
US_ONLY = JobExtraction(
    title="Backend Engineer",
    summary="Python.",
    must_have_skills=["Python"],
    location=LocationEligibility(scope=LocationScope.COUNTRIES, countries=["US"]),
)


def test_combine_blends_similarity_and_coverage() -> None:
    assert combine(0.8, None) == 0.8
    assert combine(0.8, SkillCoverage(["a", "b"], ["a"], ["b"])) == 0.65
    assert combine(-0.2, None) == 0.4  # negative cosine rescaled into 0..1


async def test_filters_hybrid_and_judge_pipeline(session: AsyncSession) -> None:
    user = await make_user(session, country="PT")
    backend = await make_job(
        session,
        "Senior Backend Engineer",
        "Python, PostgreSQL, Kafka, FastAPI services. Remote worldwide.",
        BACKEND,
        "1",
    )
    sales = await make_job(
        session,
        "Account Executive",
        "Sell software to enterprises. Salesforce, quotas, cold calling.",
        SALES,
        "2",
    )
    us_only = await make_job(
        session, "Backend Engineer", "Python. US residents only.", US_ONLY, "3"
    )

    fake = FakeLLMProvider()

    def judge(system: str, prompt: str) -> FitJudgement:
        # Cite the first evidence item verbatim, plus one bogus reference that must be dropped.
        first_line = next(line for line in prompt.splitlines() if line.startswith("E1"))
        quote = first_line.split(": ", 1)[1]
        return FitJudgement(
            score=82,
            verdict="Strong backend match; apply.",
            recommendation=Recommendation.APPLY,
            strengths=[
                EvidenceMatch(evidence_ref="E1", quote=quote, requirement="Python services"),
                EvidenceMatch(evidence_ref="E99", quote="made up", requirement="nothing"),
            ],
            gaps=["No Kafka Streams mentioned"],
        )

    fake.respond_with(judge, schema=FitJudgement)
    service = ScoringService(session, fake, judge_model="judge-model")
    report = await service.score_user(user, judge_pool=5)

    assert (
        report.considered == 3
        and report.filtered_out == 1
        and report.scored == 2
        and report.judged == 2
    )
    scores = {
        s.job_id: s
        for s in await session.scalars(select(JobScore).where(JobScore.user_id == user.id))
    }

    assert scores[us_only.id].passed_filters is False
    assert "candidate is in PT" in scores[us_only.id].filter_reasons[0]
    assert scores[us_only.id].judge_score is None

    b, s = scores[backend.id], scores[sales.id]
    assert b.passed_filters and s.passed_filters
    assert b.skill_coverage == 1.0 and s.skill_coverage == 0.0
    assert (
        b.hybrid_score is not None
        and s.hybrid_score is not None
        and b.hybrid_score > s.hybrid_score
    )
    assert b.similarity_score is not None and b.similarity_score > (s.similarity_score or 0)
    assert len(b.matched_evidence_ids) == 8

    # Judge ran on both passing jobs, in hybrid order, with the evidence listed in the prompt.
    assert [c.model for c in fake.calls] == ["judge-model", "judge-model"]
    assert (
        "E1 [" in fake.calls[0].prompt
        and "Casey" not in fake.calls[0].prompt.split("# Candidate")[0]
    )
    assert b.judge_score == 82 and b.judgement is not None
    assert b.judgement["dropped_citations"] == 1
    assert len(b.judgement["strengths"]) == 1
    assert b.judgement["strengths"][0]["path"].startswith(
        ("roles/", "projects/", "skills/", "summary")
    )
    assert b.judge_model == "judge-model" and b.judge_cost_usd == 0.0

    # Re-running is a no-op for the same profile version.
    again = await service.score_user(user, judge_pool=5)
    assert again.considered == 0 and len(fake.calls) == 2


async def test_profile_edit_invalidates_scores(session: AsyncSession) -> None:
    user = await make_user(session)
    await make_job(session, "Senior Backend Engineer", "Python.", BACKEND, "1")
    fake = FakeLLMProvider()
    fake.respond_with(
        FitJudgement(score=70, verdict="ok", recommendation=Recommendation.MAYBE),
        schema=FitJudgement,
    )
    service = ScoringService(session, fake, judge_model="j")
    first = await service.score_user(user, judge_pool=5)
    assert first.judged == 1

    doc = load_sample()
    doc.skills.append("Rust")
    await ProfileService(session, HashEmbeddingProvider()).save(user, doc)
    second = await service.score_user(user, judge_pool=5)
    assert second.profile_version == 2 and second.considered == 1 and second.judged == 1
    assert len(fake.calls) == 2


async def test_scores_are_per_user(session: AsyncSession) -> None:
    pt = await make_user(session, "pt@example.com", country="PT")
    us = await make_user(session, "us@example.com", country="US")
    await make_job(session, "Backend Engineer", "Python. US only.", US_ONLY, "1")
    fake = FakeLLMProvider()
    fake.respond_with(
        FitJudgement(score=50, verdict="v", recommendation=Recommendation.MAYBE),
        schema=FitJudgement,
    )
    service = ScoringService(session, fake, judge_model="j")
    assert (await service.score_user(pt)).filtered_out == 1
    assert (await service.score_user(us)).scored == 1
