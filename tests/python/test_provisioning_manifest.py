from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_provisioning_manifest import ProvisioningManifestError, validate

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "infrastructure/production/provisioning-manifest.r6.json"
MUTATIONS = ROOT / "infrastructure/production/external-mutation-plan.r6.json"
CADDY = ROOT / "infrastructure/production/Caddyfile.r6"


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_repository_mode_a_manifest_passes_without_external_identifiers() -> None:
    validate(MANIFEST, MUTATIONS, CADDY)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert all(
        value is None for value in manifest["generated_external_resource_identifiers"].values()
    )
    assert manifest["validation_results"]["external_mutation_count"] == 0


def test_mode_b_or_claimed_external_mutation_fails(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(manifest)
    mutated["mode"] = "CONTROLLED_PROVISIONING"
    target = tmp_path / "manifest.json"
    write_json(target, mutated)
    with pytest.raises(ProvisioningManifestError, match="Mode A"):
        validate(target, MUTATIONS, CADDY)


def test_secret_value_field_and_generated_identifier_fail(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["required_secret_values"][0]["value"] = "not-allowed"
    manifest["generated_external_resource_identifiers"]["hetzner_server_id"] = 123
    target = tmp_path / "manifest.json"
    write_json(target, manifest)
    with pytest.raises(ProvisioningManifestError):
        validate(target, MUTATIONS, CADDY)


def test_missing_rollback_or_public_admin_route_fails(tmp_path: Path) -> None:
    mutations = json.loads(MUTATIONS.read_text(encoding="utf-8"))
    mutations["mutations"][0]["rollback"] = ""
    mutation_target = tmp_path / "mutations.json"
    write_json(mutation_target, mutations)
    with pytest.raises(ProvisioningManifestError, match="rollback"):
        validate(MANIFEST, mutation_target, CADDY)

    caddy = tmp_path / "Caddyfile"
    caddy.write_text(CADDY.read_text(encoding="utf-8") + "\nreverse_proxy dozzle:8080\n")
    with pytest.raises(ProvisioningManifestError, match="exposes"):
        validate(MANIFEST, MUTATIONS, caddy)
