"""Fail-closed validation for the secret-free R6 Mode A provisioning package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MANIFEST = Path("infrastructure/production/provisioning-manifest.r6.json")
MUTATIONS = Path("infrastructure/production/external-mutation-plan.r6.json")
CADDY = Path("infrastructure/production/Caddyfile.r6")
SECRET_VALUE_PATTERN = re.compile(
    r"(?:-----BEGIN|\bsk-[A-Za-z0-9_-]{12,}|bearer\s+|api[_-]?token\s*[:=])",
    re.IGNORECASE,
)


class ProvisioningManifestError(ValueError):
    pass


def _load(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ProvisioningManifestError(f"{path.name} must contain one object")
    return loaded


def _object(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ProvisioningManifestError(f"invalid object: {key}")
    return value


def _list(parent: dict[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise ProvisioningManifestError(f"invalid list: {key}")
    return value


def validate(
    manifest_path: Path = MANIFEST,
    mutation_path: Path = MUTATIONS,
    caddy_path: Path = CADDY,
) -> None:
    manifest = _load(manifest_path)
    mutations = _load(mutation_path)
    if manifest.get("schema_version") != "boardtrace-production-provisioning/v1":
        raise ProvisioningManifestError("unsupported provisioning manifest schema")
    if manifest.get("mode") != "PLAN_AND_DRY_RUN":
        raise ProvisioningManifestError("R6 manifest must remain Mode A without explicit authority")

    static = _object(manifest, "approved_static_configuration")
    expected: dict[str, object] = {
        "provider": "Hetzner Cloud",
        "project_name": "BoardTrace Pilot",
        "region": "nbg1",
        "server_name": "boardtrace-pilot-01",
        "server_plan": "CX33",
        "os_image": "ubuntu-24.04",
        "server_count": 1,
        "public_tcp_ports": [80, 443, 48227],
        "hostname": "boardtrace.duckdns.org",
        "tls_target": "boardtrace.duckdns.org",
        "image_repository": "ghcr.io/mustafabedirr/boardtrace",
        "backup_provider": "Cloudflare R2",
        "backup_bucket": "boardtrace-pilot-backups",
        "backup_retention_days": 30,
        "backup_encryption": "age before upload",
        "age_private_key_location": "OFF_HOST_ONLY",
    }
    for key, value in expected.items():
        if static.get(key) != value:
            raise ProvisioningManifestError(f"approved static configuration mismatch: {key}")
    tag_policy = static.get("image_tag_policy")
    if not isinstance(tag_policy, str) or "latest prohibited" not in tag_policy:
        raise ProvisioningManifestError("immutable versioned GHCR image policy is required")

    identifiers = _object(manifest, "generated_external_resource_identifiers")
    if any(value is not None for value in identifiers.values()):
        raise ProvisioningManifestError("Mode A cannot claim generated external identifiers")

    secrets = _list(manifest, "required_secret_values")
    if not secrets:
        raise ProvisioningManifestError("required secret-name inventory is empty")
    for raw in secrets:
        if not isinstance(raw, dict):
            raise ProvisioningManifestError("invalid secret inventory entry")
        if raw.get("status") != "NOT_PROVIDED":
            raise ProvisioningManifestError("Mode A cannot claim a real secret is available")
        if set(raw) != {"name", "status", "storage"}:
            raise ProvisioningManifestError("secret inventory contains a value-bearing field")

    validation = _object(manifest, "validation_results")
    if validation.get("external_mutation_count") != 0:
        raise ProvisioningManifestError("Mode A external mutation count must be zero")
    if validation.get("external_provisioning") != "BLOCKED_MODE_A":
        raise ProvisioningManifestError("Mode A external provisioning must remain blocked")

    if mutations.get("schema_version") != "boardtrace-external-mutation-plan/v1":
        raise ProvisioningManifestError("unsupported mutation-plan schema")
    if (
        mutations.get("mode") != "PLAN_AND_DRY_RUN"
        or mutations.get("execution_authorized") is not False
    ):
        raise ProvisioningManifestError("external mutation execution is not authorized")
    planned = _list(mutations, "mutations")
    sequences: list[int] = []
    required_fields = {
        "sequence",
        "provider_system",
        "action",
        "resource_name",
        "purpose",
        "expected_result",
        "rollback",
        "cost_implication",
        "reversible",
        "downtime_possible",
        "required_credentials",
        "verification_command",
    }
    for raw in planned:
        if not isinstance(raw, dict) or set(raw) != required_fields:
            raise ProvisioningManifestError("mutation entry does not match the exact plan contract")
        sequence = raw.get("sequence")
        if not isinstance(sequence, int):
            raise ProvisioningManifestError("mutation sequence must be an integer")
        sequences.append(sequence)
        if not raw.get("rollback") or raw.get("reversible") is not True:
            raise ProvisioningManifestError(
                "every Mode A mutation plan needs a reversible rollback"
            )
    if sequences != list(range(1, len(planned) + 1)) or len(planned) < 12:
        raise ProvisioningManifestError("mutation plan sequence is incomplete")
    if mutations.get("execution_ledger") != [] or mutations.get("external_mutation_count") != 0:
        raise ProvisioningManifestError("Mode A ledger must remain empty with zero mutations")

    serialized = json.dumps({"manifest": manifest, "mutations": mutations}, sort_keys=True)
    if SECRET_VALUE_PATTERN.search(serialized):
        raise ProvisioningManifestError("provisioning artifacts appear to contain a secret value")

    caddy = caddy_path.read_text(encoding="utf-8")
    for required in ("admin off", "boardtrace.duckdns.org", "maintenance", "503"):
        if required not in caddy:
            raise ProvisioningManifestError("maintenance-only Caddy configuration is incomplete")
    for forbidden in ("reverse_proxy", "dozzle", "uptime-kuma", ":8080", ":3001"):
        if forbidden in caddy.lower():
            raise ProvisioningManifestError(
                "Caddy configuration exposes an application/admin route"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--mutations", type=Path, default=MUTATIONS)
    parser.add_argument("--caddy", type=Path, default=CADDY)
    args = parser.parse_args(argv)
    try:
        validate(args.manifest, args.mutations, args.caddy)
    except (OSError, json.JSONDecodeError, ProvisioningManifestError) as error:
        print(f"provisioning manifest validation failed: {error}", file=sys.stderr)
        return 1
    print("R6 Mode A provisioning manifest validation passed; external mutations=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
