"""Test fixtures.

Database tests run against a real PostgreSQL with pgvector (Docker Compose locally, a
service container in CI). The schema is created once per session with `Base.metadata`
and every test runs inside a transaction that is rolled back, so tests are isolated and
fast. Set TEST_DATABASE_URL to point somewhere else.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://jobhunt:jobhunt@localhost:5432/jobhunt_test"
    ),
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/9")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from jobhunt.core import db as db_module
from jobhunt.core.config import get_settings
from jobhunt.main import create_app
from jobhunt.models import Base


@pytest.fixture(scope="session")
async def engine():  # type: ignore[no-untyped-def]
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), poolclass=None)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # type: ignore[no-untyped-def]
    """A session bound to an outer transaction that is always rolled back."""
    async with engine.connect() as conn:
        await conn.begin()
        maker = async_sessionmaker(
            conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with maker() as sess:
            yield sess
        await conn.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client wired to the app, with the request session overridden to the test session."""
    app = create_app(get_settings())

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session
        await session.flush()

    app.dependency_overrides[db_module.get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={
            "email": "casey@example.com",
            "password": "correct-horse-battery",
            "display_name": "Casey",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
