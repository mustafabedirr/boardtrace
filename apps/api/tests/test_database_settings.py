import pytest
from pydantic import ValidationError

from boardtrace_api.config import Settings


def test_database_settings_accept_postgresql_asyncpg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BOARDTRACE_DATABASE_URL",
        "postgresql+asyncpg://user:password@db.example.test:5432/boardtrace",
    )
    settings = Settings()
    assert settings.database_url.scheme == "postgresql+asyncpg"


def test_database_pool_settings_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_DATABASE_POOL_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()
