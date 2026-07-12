import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError

from boardtrace_api.config import Environment, LogFormat, Settings


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


def test_production_wildcard_cors_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_ENVIRONMENT", "production")
    monkeypatch.setenv("BOARDTRACE_CORS_ALLOWED_ORIGINS", '["*"]')
    with pytest.raises(ValidationError, match="wildcard"):
        Settings()


def test_production_explicit_cors_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_ENVIRONMENT", "production")
    monkeypatch.setenv("BOARDTRACE_CORS_ALLOWED_ORIGINS", '["https://web.example.test"]')
    settings = Settings()
    assert settings.environment is Environment.PRODUCTION


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
