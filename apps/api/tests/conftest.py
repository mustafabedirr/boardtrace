from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings
from tests.postgres_helpers import create_test_engine, get_test_database_url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def auth_database_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_test_engine()
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def auth_sessionmaker(
    auth_database_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(auth_database_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def auth_database_session(
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with auth_sessionmaker() as session:
        try:
            await session.execute(text("TRUNCATE TABLE users CASCADE"))
            await session.commit()
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def auth_client(
    auth_database_session: AsyncSession,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            database_url=PostgresDsn(get_test_database_url()),
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        await app.state.database_engine.dispose()
