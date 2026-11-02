from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.models import Job, JobSource

pytestmark = pytest.mark.db


@pytest.fixture
async def job_id(session: AsyncSession) -> str:
    job = Job(
        source=JobSource.MANUAL,
        source_id="t1",
        url="https://x.test/t1",
        title="Backend Engineer",
        company="Acme",
        company_normalized="acme",
        description="d" * 60,
        content_hash="t1",
        fetched_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return str(job.id)


async def test_board_lifecycle(
    client: AsyncClient, auth_headers: dict[str, str], job_id: str
) -> None:
    empty = await client.get("/applications", headers=auth_headers)
    assert empty.status_code == 200 and all(v == [] for v in empty.json()["columns"].values())

    created = await client.post(
        "/applications", headers=auth_headers, json={"job_id": job_id, "note": "Found via HN"}
    )
    assert created.status_code == 201, created.text
    app = created.json()
    assert app["stage"] == "saved" and app["follow_up_at"] is None
    assert [e["kind"] for e in app["events"]] == ["stage_change", "note"]

    duplicate = await client.post("/applications", headers=auth_headers, json={"job_id": job_id})
    assert duplicate.status_code == 409

    moved = await client.patch(
        f"/applications/{app['id']}", headers=auth_headers, json={"stage": "applied"}
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["stage"] == "applied" and body["applied_at"] is not None
    follow_up = datetime.fromisoformat(body["follow_up_at"])
    assert (
        timedelta(days=6, hours=23)
        < follow_up - datetime.fromisoformat(body["applied_at"])
        < timedelta(days=7, hours=1)
    )
    assert body["follow_up_due"] is False
    assert body["events"][-1]["kind"] == "reminder"

    noted = await client.post(
        f"/applications/{app['id']}/notes", headers=auth_headers, json={"body": "Recruiter replied"}
    )
    assert noted.status_code == 201 and noted.json()["events"][-1]["body"] == "Recruiter replied"

    board = await client.get("/applications", headers=auth_headers)
    assert [a["id"] for a in board.json()["columns"]["applied"]] == [app["id"]]

    rejected = await client.patch(
        f"/applications/{app['id']}", headers=auth_headers, json={"stage": "rejected"}
    )
    assert rejected.json()["follow_up_at"] is None  # nothing left to chase

    removed = await client.delete(f"/applications/{app['id']}", headers=auth_headers)
    assert removed.status_code == 200
    assert (await client.get(f"/applications/{app['id']}", headers=auth_headers)).status_code == 404


async def test_overdue_follow_ups_are_reminders(
    client: AsyncClient, auth_headers: dict[str, str], job_id: str
) -> None:
    created = await client.post(
        "/applications", headers=auth_headers, json={"job_id": job_id, "stage": "applied"}
    )
    app_id = created.json()["id"]
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    updated = await client.patch(
        f"/applications/{app_id}", headers=auth_headers, json={"follow_up_at": past}
    )
    assert updated.json()["follow_up_due"] is True

    reminders = await client.get("/applications/reminders", headers=auth_headers)
    assert [r["id"] for r in reminders.json()] == [app_id]
    assert (await client.get("/applications", headers=auth_headers)).json()["reminders_due"] == 1

    cleared = await client.patch(
        f"/applications/{app_id}", headers=auth_headers, json={"clear_follow_up": True}
    )
    assert cleared.json()["follow_up_at"] is None
    assert (await client.get("/applications/reminders", headers=auth_headers)).json() == []


async def test_board_is_per_user(
    client: AsyncClient, auth_headers: dict[str, str], job_id: str
) -> None:
    await client.post("/applications", headers=auth_headers, json={"job_id": job_id})
    other = await client.post(
        "/auth/register", json={"email": "other@example.com", "password": "another-long-password"}
    )
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert all(
        v == []
        for v in (await client.get("/applications", headers=headers)).json()["columns"].values()
    )
