from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError

from boardtrace_api.config import Environment, LogFormat, Settings


def production_environment(monkeypatch: pytest.MonkeyPatch, stockfish_path: str) -> None:
    values = {
        "BOARDTRACE_ENVIRONMENT": "production",
        "BOARDTRACE_CORS_ALLOWED_ORIGINS": '["https://web.example.test"]',
        "BOARDTRACE_DATABASE_URL": (
            "postgresql+asyncpg://runtime:non-default@db.internal:5432/boardtrace"
        ),
        "BOARDTRACE_JWT_SIGNING_SECRET": "j" * 32,
        "BOARDTRACE_LOG_FORMAT": "json",
        "BOARDTRACE_REDIS_URL": "rediss://runtime@redis.internal:6379/0",
        "BOARDTRACE_RATE_LIMIT_ENABLED": "true",
        "BOARDTRACE_REFRESH_TOKEN_PEPPER": "p" * 32,
        "BOARDTRACE_STOCKFISH_PATH": stockfish_path,
        "BOARDTRACE_TRUSTED_HOSTS": '["api.example.test"]',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_defaults_include_local_hosts() -> None:
    settings = Settings()
    assert settings.app_name == "BoardTrace API"
    assert settings.app_version == "0.1.0"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.log_level == "INFO"
    assert settings.log_format is LogFormat.CONSOLE
    assert settings.request_id_header == "X-Request-ID"
    assert settings.cors_allowed_origins == ["http://localhost:3000"]
    assert "localhost" in settings.trusted_hosts
    assert "testserver" in settings.trusted_hosts


def test_environment_lists_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_TRUSTED_HOSTS", '["api.example.test"]')
    monkeypatch.setenv("BOARDTRACE_CORS_ALLOWED_ORIGINS", '["https://web.example.test"]')
    monkeypatch.setenv("BOARDTRACE_LOG_FORMAT", "json")
    monkeypatch.setenv("BOARDTRACE_API_V1_PREFIX", "/custom/v1")
    monkeypatch.setenv("BOARDTRACE_REQUEST_ID_HEADER", "X-Correlation-ID")
    settings = Settings()
    assert settings.trusted_hosts == ["api.example.test"]
    assert settings.cors_allowed_origins == ["https://web.example.test"]
    assert settings.log_format is LogFormat.JSON
    assert settings.api_v1_prefix == "/custom/v1"
    assert settings.request_id_header == "X-Correlation-ID"


def test_invalid_list_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_TRUSTED_HOSTS", "not-json")
    with pytest.raises(SettingsError):
        Settings()


def test_production_wildcard_cors_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stockfish = tmp_path / "stockfish"
    stockfish.write_text("fixture")
    stockfish.chmod(0o755)
    production_environment(monkeypatch, str(stockfish))
    monkeypatch.setenv("BOARDTRACE_CORS_ALLOWED_ORIGINS", '["*"]')
    with pytest.raises(ValidationError, match="wildcard"):
        Settings()


def test_production_explicit_configuration_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stockfish = tmp_path / "stockfish"
    stockfish.write_text("fixture")
    stockfish.chmod(0o755)
    production_environment(monkeypatch, str(stockfish))
    settings = Settings()
    assert settings.environment is Environment.PRODUCTION


@pytest.mark.parametrize(
    "variable",
    [
        "BOARDTRACE_DATABASE_URL",
        "BOARDTRACE_JWT_SIGNING_SECRET",
        "BOARDTRACE_REDIS_URL",
        "BOARDTRACE_REFRESH_TOKEN_PEPPER",
        "BOARDTRACE_STOCKFISH_PATH",
    ],
)
def test_production_missing_critical_configuration_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    variable: str,
) -> None:
    stockfish = tmp_path / "stockfish"
    stockfish.write_text("fixture")
    stockfish.chmod(0o755)
    production_environment(monkeypatch, str(stockfish))
    monkeypatch.delenv(variable)

    with pytest.raises(ValidationError, match="requires explicit"):
        Settings()


def test_production_rejects_development_network_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stockfish = tmp_path / "stockfish"
    stockfish.write_text("fixture")
    stockfish.chmod(0o755)
    production_environment(monkeypatch, str(stockfish))
    monkeypatch.setenv("BOARDTRACE_TRUSTED_HOSTS", '["localhost"]')

    with pytest.raises(ValidationError, match="trusted hosts"):
        Settings()


def test_production_rejects_invalid_stockfish_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    production_environment(monkeypatch, str(tmp_path / "missing-stockfish"))

    with pytest.raises(ValidationError, match="Stockfish"):
        Settings()


@pytest.mark.parametrize(
    ("variable", "value"),
    [("BOARDTRACE_ENVIRONMENT", "invalid"), ("BOARDTRACE_LOG_FORMAT", "plain")],
)
def test_invalid_enum_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        Settings()


def test_default_cors_origins_do_not_include_extension_placeholder() -> None:
    assert not any(
        origin.startswith("chrome-extension://") for origin in Settings().cors_allowed_origins
    )
