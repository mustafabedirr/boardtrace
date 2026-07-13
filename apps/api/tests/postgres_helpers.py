import os

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


def get_test_database_url() -> str:
    url = os.environ.get("BOARDTRACE_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("BOARDTRACE_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not url.startswith("postgresql+asyncpg://") or not url.endswith("/boardtrace_test"):
        pytest.fail(
            "BOARDTRACE_TEST_DATABASE_URL must identify the isolated boardtrace_test database"
        )
    return url


def create_test_engine() -> AsyncEngine:
    return create_async_engine(get_test_database_url(), pool_pre_ping=True, poolclass=NullPool)
