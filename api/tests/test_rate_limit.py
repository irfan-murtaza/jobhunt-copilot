"""The rate limiter is disabled in most tests, so exercise it explicitly here.

slowapi attaches rate-limit headers to the response object of a decorated endpoint; an
endpoint missing the `response` parameter fails with a 500 only when the limiter is on.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from jobhunt.core.ratelimit import limiter

pytestmark = pytest.mark.db


@pytest.fixture
def limiter_on() -> Iterator[None]:
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


async def test_limited_endpoint_works_and_enforces_its_limit(
    client: AsyncClient, auth_headers: dict[str, str], limiter_on: None
) -> None:
    # No profile yet, so each allowed call is a 409; the limit is 2 per minute.
    first = await client.post("/matches/score/sync", headers=auth_headers)
    second = await client.post("/matches/score/sync", headers=auth_headers)
    third = await client.post("/matches/score/sync", headers=auth_headers)
    assert [first.status_code, second.status_code, third.status_code] == [409, 409, 429]


async def test_limited_endpoint_returns_rate_limit_headers(
    client: AsyncClient,
    auth_headers: dict[str, str],
    limiter_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jobhunt.api.routes import matches

    async def fake_enqueue(*_: object, **__: object) -> str:
        return "job-1"

    monkeypatch.setattr(matches, "enqueue", fake_enqueue)
    response = await client.post("/matches/score", headers=auth_headers)
    assert response.status_code == 202, response.text
    assert response.headers["x-ratelimit-limit"] == "5"
