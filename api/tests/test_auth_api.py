import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db

CREDS = {"email": "Casey@Example.com", "password": "correct-horse-battery"}


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "x-request-id" in response.headers


async def test_register_login_me_flow(client: AsyncClient) -> None:
    created = await client.post("/auth/register", json=CREDS)
    assert created.status_code == 201, created.text
    assert "jobhunt_refresh" in created.cookies

    duplicate = await client.post("/auth/register", json=CREDS)
    assert duplicate.status_code == 409

    login = await client.post("/auth/login", json=CREDS)
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "casey@example.com"  # normalised to lower case


async def test_wrong_password_and_unknown_user_look_identical(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDS)
    wrong = await client.post("/auth/login", json={**CREDS, "password": "nope-nope-nope"})
    unknown = await client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "x" * 12}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_short_password_rejected(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={**CREDS, "password": "short"})
    assert response.status_code == 422


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401
    bad = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_refresh_rotates_access_token(client: AsyncClient) -> None:
    created = await client.post("/auth/register", json=CREDS)
    assert created.status_code == 201
    # The client keeps the httpOnly refresh cookie, exactly as a browser would.
    refreshed = await client.post("/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    client.cookies.clear()
    no_cookie = await client.post("/auth/refresh")
    assert no_cookie.status_code == 401
