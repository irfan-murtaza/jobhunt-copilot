from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from helpers import load_sample
from jobhunt.ai.factory import get_llm_provider
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.schemas.profile import ProfileDocument, Role

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def fake_llm(client: AsyncClient) -> AsyncIterator[FakeLLMProvider]:
    fake = FakeLLMProvider()
    fake.respond_with(load_sample(), schema=ProfileDocument)
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


async def test_profile_404_before_upload(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assert (await client.get("/profile", headers=auth_headers)).status_code == 404
    assert (await client.get("/profile/evidence", headers=auth_headers)).json() == []


async def test_upload_parses_saves_and_embeds(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider, tmp_path: Path
) -> None:
    from jobhunt.core.config import get_settings

    get_settings().upload_dir = str(tmp_path)
    files = {"resume": ("resume.pdf", (FIXTURES / "resume.pdf").read_bytes(), "application/pdf")}
    response = await client.post("/profile/upload", headers=auth_headers, files=files)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["document"]["name"] == "Casey Rivera"
    assert body["evidence_count"] > 10
    assert body["source_filename"] == "resume.pdf"

    # The LLM saw the extracted resume text, routed to the extraction model.
    call = fake_llm.calls[0]
    assert "Northwind Analytics" in call.prompt
    assert call.model == get_settings().model_extract
    assert call.effort == "low"

    # Original upload kept under the user's folder.
    saved = list(tmp_path.rglob("*.pdf"))
    assert len(saved) == 1

    evidence = (await client.get("/profile/evidence", headers=auth_headers)).json()
    paths = {e["path"] for e in evidence}
    assert "roles/0/bullets/0" in paths and "summary" in paths


async def test_upload_with_linkedin_export_merges_both_texts(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider, tmp_path: Path
) -> None:
    from jobhunt.core.config import get_settings

    get_settings().upload_dir = str(tmp_path)
    files = {
        "resume": (
            "resume.docx",
            (FIXTURES / "resume.docx").read_bytes(),
            "application/octet-stream",
        ),
        "linkedin": ("linkedin.pdf", (FIXTURES / "resume.pdf").read_bytes(), "application/pdf"),
    }
    response = await client.post("/profile/upload", headers=auth_headers, files=files)
    assert response.status_code == 201, response.text
    assert "<linkedin_export>" in fake_llm.calls[0].prompt


async def test_upload_rejects_unsupported_files(
    client: AsyncClient, auth_headers: dict[str, str], fake_llm: FakeLLMProvider
) -> None:
    files = {"resume": ("resume.txt", b"plain text resume " * 10, "text/plain")}
    response = await client.post("/profile/upload", headers=auth_headers, files=files)
    assert response.status_code == 422
    assert fake_llm.calls == []


async def test_edit_bumps_version_and_rebuilds_evidence(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    doc = ProfileDocument(
        name="Casey Rivera",
        skills=["Python"],
        roles=[
            Role(title="Engineer", company="Acme", start="2020", bullets=["Built X", "Shipped Y"])
        ],
    )
    first = await client.put("/profile", headers=auth_headers, json=doc.model_dump(mode="json"))
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert first.json()["evidence_count"] == 3  # two bullets + one skill

    doc.roles[0].bullets.append("Led Z")
    second = await client.put("/profile", headers=auth_headers, json=doc.model_dump(mode="json"))
    assert second.json()["version"] == 2
    assert second.json()["evidence_count"] == 4

    evidence = (await client.get("/profile/evidence", headers=auth_headers)).json()
    assert len(evidence) == 4  # old rows were replaced, not appended


async def test_profile_is_isolated_per_user(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    doc = ProfileDocument(name="Casey Rivera", skills=["Python"])
    await client.put("/profile", headers=auth_headers, json=doc.model_dump(mode="json"))

    other = await client.post(
        "/auth/register", json={"email": "other@example.com", "password": "another-long-password"}
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get("/profile", headers=other_headers)).status_code == 404
