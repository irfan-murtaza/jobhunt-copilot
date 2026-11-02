import pytest
from httpx import AsyncClient

from jobhunt.ai.factory import get_llm_provider
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.schemas.job import JobExtraction, LocationEligibility, LocationScope

pytestmark = pytest.mark.db


@pytest.fixture
def fake_llm(client: AsyncClient) -> FakeLLMProvider:
    fake = FakeLLMProvider()
    fake.respond_with(
        JobExtraction(
            title="Senior Backend Engineer",
            company="Acme Robotics",
            must_have_skills=["Python"],
            location=LocationEligibility(scope=LocationScope.WORLDWIDE),
            summary="Backend engineering role.",
        ),
        schema=JobExtraction,
    )
    client._transport.app.dependency_overrides[get_llm_provider] = lambda: fake  # type: ignore[attr-defined]
    return fake


async def test_manual_job_from_description_is_extracted_and_listed(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider
) -> None:
    body = {
        "description": "We are hiring a Senior Backend Engineer at Acme Robotics. 5+ years Python. Remote anywhere."
    }
    created = await client.post("/jobs/manual", headers=auth_headers, json=body)
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["source"] == "manual"
    assert (
        job["title"] == "Senior Backend Engineer" and job["company"] == "Acme Robotics"
    )  # filled from extraction
    assert job["extraction"]["location"]["scope"] == "worldwide"
    assert job["extraction_status"] == "done" and job["is_duplicate"] is False

    listed = await client.get("/jobs", headers=auth_headers, params={"q": "acme"})
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == job["id"]

    detail = await client.get(f"/jobs/{job['id']}", headers=auth_headers)
    assert detail.status_code == 200 and "5+ years Python" in detail.json()["description"]


async def test_manual_job_requires_url_or_description(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider
) -> None:
    assert (await client.post("/jobs/manual", headers=auth_headers, json={})).status_code == 422
    short = await client.post(
        "/jobs/manual", headers=auth_headers, json={"description": "too short"}
    )
    assert short.status_code == 422


async def test_manual_job_rejects_private_urls(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider
) -> None:
    for url in (
        "http://localhost:8000/x",
        "http://127.0.0.1/x",
        "ftp://example.com/x",
        "http://169.254.169.254/latest",
    ):
        response = await client.post("/jobs/manual", headers=auth_headers, json={"url": url})
        assert response.status_code == 422, url
    assert fake_llm.calls == []


async def test_sources_endpoint_lists_configured_sources(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/jobs/sources", headers=auth_headers)
    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert {"remotive", "remoteok", "weworkremotely", "hackernews"} <= names
    assert all(s["attribution"] for s in response.json())


async def test_jobs_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/jobs")).status_code == 401
