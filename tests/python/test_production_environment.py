from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.validate_production_environment import (
    ProductionEnvironmentError,
    load_contract,
    validate_environment,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "infrastructure/production/production-environment-contract.json"


@pytest.fixture
def complete_environment() -> dict[str, str]:
    contract = load_contract(CONTRACT)
    secret_names = contract["required_secret"]
    non_secret_names = contract["required_non_secret"]
    assert isinstance(secret_names, list)
    assert isinstance(non_secret_names, list)
    names = secret_names + non_secret_names
    env = {str(name): "fixture-value-not-a-credential" for name in names}
    env.update(
        {
            "BOARDTRACE_ENVIRONMENT": "production",
            "BOARDTRACE_LOG_FORMAT": "json",
            "BOARDTRACE_CORS_ALLOWED_ORIGINS": '["https://boardtrace.duckdns.org"]',
            "BOARDTRACE_TRUSTED_HOSTS": '["boardtrace.duckdns.org"]',
            "BOARDTRACE_ANALYSIS_QUEUE_NAME": "boardtrace.analysis.jobs",
            "BOARDTRACE_RATE_LIMIT_ENABLED": "true",
            "BOARDTRACE_ANALYSIS_AUTOMATIC_RETRY_ENABLED": "false",
            "BOARDTRACE_ANALYSIS_TASK_SOFT_TIME_LIMIT_SECONDS": "170",
            "BOARDTRACE_ANALYSIS_TASK_TIME_LIMIT_SECONDS": "180",
            "BOARDTRACE_PUBLIC_HOSTNAME": "boardtrace.duckdns.org",
            "BOARDTRACE_PUBLIC_API_URL": "https://boardtrace.duckdns.org",
            "BOARDTRACE_API_URL": "https://boardtrace.duckdns.org",
            "BOARDTRACE_EXTENSION_API_BASE_URL": "https://boardtrace.duckdns.org",
            "BOARDTRACE_R2_BUCKET": "boardtrace-pilot-backups",
            "BOARDTRACE_GHCR_IMAGE": "ghcr.io/mustafabedirr/boardtrace",
            "BOARDTRACE_SSH_PORT": "48227",
            "BOARDTRACE_SSH_KEY_AUTHENTICATION": "required",
            "BOARDTRACE_SSH_PASSWORD_AUTHENTICATION": "disabled",
            "BOARDTRACE_ADMIN_PANELS_PUBLIC": "false",
            "BOARDTRACE_ANALYSIS_RESULT_POLICY": "session-only",
            "BOARDTRACE_GAME_DATA_RETENTION_POLICY": "delete-on-terminal",
            "BOARDTRACE_PROVENANCE_RETENTION_POLICY": "delete-on-terminal",
            "BOARDTRACE_DIAGNOSTIC_LOG_POLICY": "metadata-only",
            "BOARDTRACE_RAW_GAME_LOGGING": "prohibited",
        }
    )
    return env


def test_complete_safe_fixture_passes(complete_environment: dict[str, str]) -> None:
    validate_environment(complete_environment, load_contract(CONTRACT))


def test_every_required_category_fails_independently(
    complete_environment: dict[str, str],
) -> None:
    contract = load_contract(CONTRACT)
    for category in ("required_secret", "required_non_secret"):
        names = contract[category]
        assert isinstance(names, list)
        for name in names:
            assert isinstance(name, str)
            mutated = copy.deepcopy(complete_environment)
            del mutated[name]
            with pytest.raises(ProductionEnvironmentError, match=name):
                validate_environment(mutated, contract)


def test_placeholder_and_partial_environment_fail_without_value_disclosure(
    complete_environment: dict[str, str],
) -> None:
    mutated = copy.deepcopy(complete_environment)
    marker = "<required-secret-do-not-print>"
    mutated["BOARDTRACE_GHCR_TOKEN"] = marker
    with pytest.raises(ProductionEnvironmentError) as raised:
        validate_environment(mutated, load_contract(CONTRACT))
    assert "BOARDTRACE_GHCR_TOKEN" in str(raised.value)
    assert marker not in str(raised.value)
    with pytest.raises(ProductionEnvironmentError):
        validate_environment({}, load_contract(CONTRACT))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("BOARDTRACE_PUBLIC_HOSTNAME", "localhost"),
        ("BOARDTRACE_PUBLIC_API_URL", "http://localhost:8000"),
        ("BOARDTRACE_R2_BUCKET", "wrong-bucket"),
        ("BOARDTRACE_GHCR_IMAGE", "example.invalid/image"),
        ("BOARDTRACE_ADMIN_PANELS_PUBLIC", "true"),
        ("BOARDTRACE_SSH_PASSWORD_AUTHENTICATION", "enabled"),
        ("BOARDTRACE_ANALYSIS_RESULT_POLICY", "persistent-history"),
        ("BOARDTRACE_DIAGNOSTIC_LOG_POLICY", "full-pgn"),
        ("BOARDTRACE_RAW_GAME_LOGGING", "allowed"),
    ],
)
def test_unsafe_production_values_fail(
    complete_environment: dict[str, str], key: str, value: str
) -> None:
    mutated = copy.deepcopy(complete_environment)
    mutated[key] = value
    with pytest.raises(ProductionEnvironmentError, match=key):
        validate_environment(mutated, load_contract(CONTRACT))


def test_cli_exposes_no_force_or_skip_bypass() -> None:
    source = (ROOT / "scripts/validate_production_environment.py").read_text(encoding="utf-8")
    assert "--force" not in source
    assert "--skip" not in source


def test_superseded_pgn_retention_key_is_rejected(
    complete_environment: dict[str, str],
) -> None:
    complete_environment["BOARDTRACE_PGN_LOG_RETENTION_HOURS"] = "24"
    with pytest.raises(ProductionEnvironmentError, match="superseded"):
        validate_environment(complete_environment, load_contract(CONTRACT))
