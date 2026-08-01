"""No-bypass, secret-safe BoardTrace production environment preflight."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

CONTRACT = Path("infrastructure/production/production-environment-contract.json")
PLACEHOLDER_MARKERS = ("<required", "replace-with", "change-me", "example", "placeholder")


class ProductionEnvironmentError(ValueError):
    """Contains key names and policy errors, never supplied values."""


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
        raise ProductionEnvironmentError("production environment contract is invalid")
    return loaded


def _names(contract: Mapping[str, object], category: str) -> tuple[str, ...]:
    raw = contract.get(category)
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ProductionEnvironmentError(f"contract category is invalid: {category}")
    return tuple(raw)


def _require_exact(env: Mapping[str, str], name: str, expected: str, errors: list[str]) -> None:
    if env.get(name) != expected:
        errors.append(f"{name} must match approved production policy")


def _https_url(env: Mapping[str, str], name: str, hostname: str, errors: list[str]) -> None:
    parsed = urlsplit(env.get(name, ""))
    if (
        parsed.scheme != "https"
        or parsed.hostname != hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        errors.append(f"{name} must use the approved non-local HTTPS endpoint")


def validate_environment(
    env: Mapping[str, str], contract: Mapping[str, object] | None = None
) -> None:
    resolved = contract or load_contract()
    required = _names(resolved, "required_secret") + _names(resolved, "required_non_secret")
    errors: list[str] = []
    for name in required:
        raw = env.get(name)
        if raw is None or not raw.strip():
            errors.append(f"missing required key: {name}")
        elif any(marker in raw.lower() for marker in PLACEHOLDER_MARKERS):
            errors.append(f"placeholder rejected for key: {name}")

    _require_exact(env, "BOARDTRACE_ENVIRONMENT", "production", errors)
    _require_exact(env, "BOARDTRACE_LOG_FORMAT", "json", errors)
    _require_exact(env, "BOARDTRACE_PUBLIC_HOSTNAME", "boardtrace.duckdns.org", errors)
    _require_exact(env, "BOARDTRACE_R2_BUCKET", "boardtrace-pilot-backups", errors)
    _require_exact(env, "BOARDTRACE_GHCR_IMAGE", "ghcr.io/mustafabedirr/boardtrace", errors)
    _require_exact(env, "BOARDTRACE_ANALYSIS_QUEUE_NAME", "boardtrace.analysis.jobs", errors)
    _require_exact(env, "BOARDTRACE_RATE_LIMIT_ENABLED", "true", errors)
    _require_exact(env, "BOARDTRACE_ANALYSIS_AUTOMATIC_RETRY_ENABLED", "false", errors)
    _require_exact(env, "BOARDTRACE_ANALYSIS_TASK_SOFT_TIME_LIMIT_SECONDS", "170", errors)
    _require_exact(env, "BOARDTRACE_ANALYSIS_TASK_TIME_LIMIT_SECONDS", "180", errors)
    _require_exact(env, "BOARDTRACE_SSH_PORT", "48227", errors)
    _require_exact(env, "BOARDTRACE_SSH_KEY_AUTHENTICATION", "required", errors)
    _require_exact(env, "BOARDTRACE_SSH_PASSWORD_AUTHENTICATION", "disabled", errors)
    _require_exact(env, "BOARDTRACE_ADMIN_PANELS_PUBLIC", "false", errors)
    _require_exact(env, "BOARDTRACE_ANALYSIS_RESULT_POLICY", "session-only", errors)
    _require_exact(env, "BOARDTRACE_GAME_DATA_RETENTION_POLICY", "delete-on-terminal", errors)
    _require_exact(env, "BOARDTRACE_PROVENANCE_RETENTION_POLICY", "delete-on-terminal", errors)
    _require_exact(env, "BOARDTRACE_DIAGNOSTIC_LOG_POLICY", "metadata-only", errors)
    _require_exact(env, "BOARDTRACE_RAW_GAME_LOGGING", "prohibited", errors)
    if "BOARDTRACE_PGN_LOG_RETENTION_HOURS" in env:
        errors.append("BOARDTRACE_PGN_LOG_RETENTION_HOURS is superseded and must be absent")

    hostname = env.get("BOARDTRACE_PUBLIC_HOSTNAME", "")
    if re.fullmatch(r"[a-z0-9-]+\.duckdns\.org", hostname) is None:
        errors.append("BOARDTRACE_PUBLIC_HOSTNAME must be a valid DuckDNS hostname")
    for name in (
        "BOARDTRACE_PUBLIC_API_URL",
        "BOARDTRACE_API_URL",
        "BOARDTRACE_EXTENSION_API_BASE_URL",
    ):
        _https_url(env, name, "boardtrace.duckdns.org", errors)

    cors = env.get("BOARDTRACE_CORS_ALLOWED_ORIGINS", "")
    trusted = env.get("BOARDTRACE_TRUSTED_HOSTS", "")
    if "localhost" in cors.lower() or "127.0.0.1" in cors:
        errors.append("BOARDTRACE_CORS_ALLOWED_ORIGINS must not contain local hosts")
    if "boardtrace.duckdns.org" not in cors:
        errors.append("BOARDTRACE_CORS_ALLOWED_ORIGINS must contain the approved host")
    if "localhost" in trusted.lower() or "127.0.0.1" in trusted:
        errors.append("BOARDTRACE_TRUSTED_HOSTS must not contain local hosts")
    if "boardtrace.duckdns.org" not in trusted:
        errors.append("BOARDTRACE_TRUSTED_HOSTS must contain the approved host")

    if env.get("BOARDTRACE_DEBUG", "false").lower() == "true":
        errors.append("BOARDTRACE_DEBUG must not enable development behavior")
    if env.get("BOARDTRACE_DATABASE_ECHO", "false").lower() == "true":
        errors.append("BOARDTRACE_DATABASE_ECHO must not expose SQL in production")
    if errors:
        raise ProductionEnvironmentError("; ".join(sorted(set(errors))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the complete BoardTrace production environment. No bypass exists."
    )
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    args = parser.parse_args(argv)
    try:
        validate_environment(os.environ, load_contract(args.contract))
    except (OSError, json.JSONDecodeError, ProductionEnvironmentError) as error:
        print(f"production environment preflight failed: {error}", file=sys.stderr)
        return 1
    print("production environment preflight passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
