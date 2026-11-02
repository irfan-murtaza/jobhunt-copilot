from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from helpers import load_sample
from jobhunt.ai.factory import get_llm_provider
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.models import ExtractionStatus, Job, JobSource
from jobhunt.schemas.job import JobExtraction, LocationEligibility, LocationScope
from jobhunt.schemas.scoring import FitJudgement, Recommendation

pytestmark = pytest.mark.db


@pytest.fixture
async def seeded(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> dict[str, str]:
    await client.put("/profile", headers=auth_headers, json=load_sample().model_dump(mode="json"))
    extraction = JobExtraction(
        title="Senior Backend Engineer",
        summary="Python.",
        must_have_skills=["Python"],
        location=LocationEligibility(scope=LocationScope.WORLDWIDE),
    )
    job = Job(
        source=JobSource.REMOTIVE,
        source_id="1",
        url="https://x.test/1",
        title="Senior Backend Engineer",
        company="Acme",
        company_normalized="acme",
        description="Python services.",
        content_hash="h",
        fetched_at=datetime.now(UTC),
        extraction=extraction.model_dump(mode="json"),
        extraction_status=ExtractionStatus.DONE,
    )
    session.add(job)
    await session.flush()
    job.dedup_group_id = job.id
    from jobhunt.ai.embeddings import HashEmbeddingProvider

    [job.embedding] = await HashEmbeddingProvider().embed(
        ["Senior Backend Engineer Python services"]
    )
    await session.flush()
    fake = FakeLLMProvider()
    fake.respond_with(
        FitJudgement(
            score=77, verdict="Apply.", recommendation=Recommendation.APPLY, gaps=["Kafka"]
        ),
        schema=FitJudgement,
    )
    client._transport.app.dependency_overrides[get_llm_provider] = lambda: fake  # type: ignore[attr-defined]
    return {"job_id": str(job.id)}


async def test_preferences_roundtrip_and_validation(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    default = await client.get("/preferences", headers=auth_headers)
    assert default.status_code == 200 and default.json()["shortlist_size"] == 10

    update = {
        "country": "pk",
        "timezone": "Asia/Karachi",
        "min_salary_usd": 60000,
        "seniority_levels": ["senior"],
        "excluded_keywords": ["crypto"],
        "required_keywords": [],
        "shortlist_size": 5,
        "judge_pool_size": 20,
        "digest_email_enabled": False,
    }
    saved = await client.put("/preferences", headers=auth_headers, json=update)
    assert saved.status_code == 200, saved.text
    assert saved.json()["country"] == "PK" and saved.json()["judge_pool_size"] == 20

    bad = await client.put(
        "/preferences", headers=auth_headers, json={**update, "timezone": "Mars/Olympus"}
    )
    assert bad.status_code == 422


async def test_sync_scoring_then_ranked_matches_with_reasoning(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    summary = await client.post(
        "/matches/score/sync", headers=auth_headers, params={"judge_pool": 5}
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["scored"] == 1 and summary.json()["judged"] == 1

    matches = await client.get("/matches", headers=auth_headers)
    assert matches.status_code == 200 and matches.json()["total"] == 1
    item = matches.json()["items"][0]
    assert item["judge_score"] == 77 and item["judgement"]["gaps"] == ["Kafka"]
    assert item["skill_coverage"] == 1.0 and item["passed_filters"] is True

    detail = await client.get(f"/matches/{seeded['job_id']}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["skills"]["matched"] == ["Python"]
    assert len(body["matched_evidence"]) == 8 and body["matched_evidence"][0]["path"]

    assert (await client.get("/matches", headers=auth_headers, params={"min_score": 90})).json()[
        "total"
    ] == 0


async def test_scoring_without_profile_is_a_conflict(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    fake = FakeLLMProvider()
    client._transport.app.dependency_overrides[get_llm_provider] = lambda: fake  # type: ignore[attr-defined]
    response = await client.post("/matches/score/sync", headers=auth_headers)
    assert response.status_code == 409


async def test_judge_one_job_on_demand(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    response = await client.post(f"/matches/{seeded['job_id']}/judge", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["judgement"]["recommendation"] == "apply"
