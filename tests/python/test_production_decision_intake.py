from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_production_decisions import (
    DecisionValidationError,
    load_single_mapping,
    validate_mapping,
)

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / "docs/production/decisions/boardtrace-production-decision-package.v1.0-pilot.json"


@pytest.fixture
def mapping() -> dict[str, object]:
    loaded = json.loads(MAPPING.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def decisions(mapping: dict[str, object]) -> list[dict[str, object]]:
    value = mapping["decisions"]
    assert isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return value


def decision(mapping: dict[str, object], decision_id: str) -> dict[str, object]:
    return next(item for item in decisions(mapping) if item["id"] == decision_id)


def value(mapping: dict[str, object], decision_id: str) -> dict[str, object]:
    result = decision(mapping, decision_id)["value"]
    assert isinstance(result, dict)
    return result


def risk(mapping: dict[str, object], risk_id: str) -> dict[str, object]:
    risks = mapping["risks"]
    assert isinstance(risks, list)
    return next(item for item in risks if isinstance(item, dict) and item["id"] == risk_id)


def test_all_28_decisions_are_complete_while_provisioning_and_deployment_are_blocked(
    mapping: dict[str, object],
) -> None:
    summary = validate_mapping(mapping)
    assert summary.mandatory_field_count == 28
    assert summary.resolved_field_count == 28
    assert summary.decided_field_count == 21
    assert summary.pending_provisioning_field_count == 7
    assert summary.missing_decision_field_count == 0
    assert summary.invalid_field_count == summary.conflict_count == 0
    assert summary.decision_completeness == "PASS"
    assert summary.external_provisioning_completeness == "BLOCKED"
    assert summary.deployment_executability == "BLOCKED"


def test_rate_limit_policy_rejects_fail_open_missing_retry_after_and_invalid_limits(
    mapping: dict[str, object],
) -> None:
    for field, invalid, match in (
        ("redis_failure", "FAIL_OPEN", "fail-open"),
        ("retry_after_required", False, "Retry-After"),
        ("analysis_start_window_minutes", -1, "positive integer"),
    ):
        mutated = copy.deepcopy(mapping)
        value(mutated, "D20R2-012")[field] = invalid
        with pytest.raises(DecisionValidationError, match=match):
            validate_mapping(mutated)


def test_rate_limit_policy_restricts_anonymous_health_and_uses_masked_redis_state(
    mapping: dict[str, object],
) -> None:
    policy = value(mapping, "D20R2-012")
    assert policy["anonymous_api"] == "PROHIBITED_EXCEPT_MINIMUM_HEALTH"
    assert policy["health_exposes_metadata"] is False
    assert policy["state_backend"] == "REDIS_SHARED"
    assert policy["log_retention_days"] == 7
    assert policy["masked_log_identity"] is True


def test_on_call_roles_are_named_scoped_and_fail_closed(mapping: dict[str, object]) -> None:
    policy = value(mapping, "D20R2-014")
    assert policy["primary_on_call"] == policy["incident_commander"] == "Mustafa Bedir"
    assert policy["secondary_on_call"] == "Ahmet Bedir"
    assert policy["secondary_access_provisioned"] is False
    assert policy["sev1_fail_closed"] is True
    assert policy["severity_response_minutes"] == {"SEV-1": 15, "SEV-2": 60, "SEV-3": 1440}
    assert policy["post_incident_review"] == {
        "SEV-1": "MANDATORY",
        "SEV-2": "MANDATORY",
        "SEV-3": "OPTIONAL",
    }


def test_pitr_disabled_is_an_explicit_decision_with_rpo_and_triggers(
    mapping: dict[str, object],
) -> None:
    policy = value(mapping, "D20R2-015")
    assert decision(mapping, "D20R2-015")["status"] == "DECIDED"
    assert policy["pitr"] == "DISABLED_FOR_CLOSED_PILOT"
    assert policy["rpo_hours"] == 24
    assert policy["reassessment_triggers"]


def test_privacy_provenance_and_communication_policies_are_complete(
    mapping: dict[str, object],
) -> None:
    privacy = value(mapping, "D20R2-016")
    assert privacy["data_minimization"] is True
    assert privacy["deletion_deadline_days"] == 30
    assert privacy["security_log_retention_days"] == 7
    assert privacy["sharing"] == "LEGAL_NECESSITY_ONLY"
    assert privacy["identity_verification"] == "REGISTERED_EMAIL_LINK_OR_CODE"
    assert privacy["privacy_notice_before_processing"] is True
    provenance = value(mapping, "D20R2-017")
    assert provenance["delete_at_terminal_state"] is True
    assert provenance["source_mismatch"] == "FAIL_CLOSED"
    assert provenance["runtime_mutable_allowlist"] is False
    assert provenance["error_log_retention_days"] == 7
    communication = value(mapping, "D20R2-018")
    assert communication["initial_notice_minutes"] == {"SEV-1": 30, "SEV-2": 120}
    assert communication["update_minutes"] == {"SEV-1": 60, "SEV-2": 240}
    assert communication["planned_maintenance_notice_hours"] == 24
    assert communication["emergency_maintenance_without_notice"] is True


def test_conditional_launch_window_does_not_grant_launch(mapping: dict[str, object]) -> None:
    policy = value(mapping, "D20R2-019")
    assert policy["grants_launch_authorization"] is False
    assert policy["public_launch"] == "NOT_GRANTED"
    summary = validate_mapping(mapping)
    assert summary.closed_pilot_launch_authorization == "NOT_YET_GRANTED"
    assert summary.public_launch_authorization == "NOT_GRANTED"


def test_eight_distinct_signoffs_disclose_absent_independence(mapping: dict[str, object]) -> None:
    summary = validate_mapping(mapping)
    assert summary.sign_off_count == 8
    roles = []
    for number in range(20, 28):
        signoff = value(mapping, f"D20R2-{number:03d}")
        roles.append(signoff["role"])
        assert signoff["accountable_person"] == "Mustafa Bedir"
        assert signoff["approval"] == "APPROVED"
        assert signoff["independent_review"] == "ABSENT"
        assert signoff["role_concentration_risk"] == "R4-003"
    assert len(set(roles)) == 8


def test_risk_register_is_accountable_and_open_mitigations_remain_blockers(
    mapping: dict[str, object],
) -> None:
    summary = validate_mapping(mapping)
    assert summary.active_accept_risk_count == 5
    assert summary.active_mitigate_risk_count == 3
    assert summary.expired_risk_count == 0
    assert summary.deployment_blocking_risk_count == 3
    assert all(
        risk(mapping, f"R4-{number:03d}")["owner"] == "Mustafa Bedir" for number in range(1, 12)
    )
    controls = risk(mapping, "R4-009")["controls"]
    assert isinstance(controls, list)
    assert controls[-1] == "prohibit manual bypass"
    for risk_id in ("R4-010", "R4-011"):
        closed = risk(mapping, risk_id)
        assert closed["disposition"] == "CLOSED"
        assert closed["state"] == "VERIFIED"
        assert closed["deployment_blocker"] is False
        assert closed["implementation_evidence"]


def test_expired_acceptance_and_false_mitigation_completion_fail_safely(
    mapping: dict[str, object],
) -> None:
    expired = copy.deepcopy(mapping)
    risk(expired, "R4-002")["disposition"] = "EXPIRED"
    risk(expired, "R4-002")["deployment_blocker"] = False
    with pytest.raises(DecisionValidationError, match="expired risk"):
        validate_mapping(expired)
    fake = copy.deepcopy(mapping)
    risk(fake, "R4-010")["disposition"] = "MITIGATE"
    risk(fake, "R4-010")["state"] = "OPEN"
    risk(fake, "R4-010")["deployment_blocker"] = True
    risk(fake, "R4-010")["implementation_evidence"] = ["plan only"]
    with pytest.raises(DecisionValidationError, match="cannot claim"):
        validate_mapping(fake)


def test_superseded_password_ssh_and_live_game_invariant_are_explicit(
    mapping: dict[str, object],
) -> None:
    ssh = risk(mapping, "R4-001")
    controls = ssh["controls"]
    assert isinstance(controls, list)
    assert "enable SSH keys" in controls
    assert "disable password authentication" in controls
    assert mapping["invariant"] == "NO ENGINE OUTPUT DURING LIVE GAMES"


def test_metadata_only_logging_supersedes_full_pgn_without_granting_launch(
    mapping: dict[str, object],
) -> None:
    policy = value(mapping, "D20R2-016")["diagnostic_logging"]
    assert isinstance(policy, dict)
    assert policy["active_policy"] == "METADATA_ONLY"
    for field in (
        "full_pgn",
        "fen",
        "raw_move_lists",
        "game_request_bodies",
        "reconstructable_engine_io",
    ):
        assert policy[field] == "PROHIBITED"
    superseded = risk(mapping, "R4-005")
    assert superseded["disposition"] == "CLOSED"
    assert superseded["state"] == "SUPERSEDED"
    summary = validate_mapping(mapping)
    assert summary.decision_completeness == "PASS"
    assert summary.conflict_count == 0
    assert summary.deployment_executability == "BLOCKED"
    assert summary.closed_pilot_launch_authorization == "NOT_YET_GRANTED"
    assert summary.public_launch_authorization == "NOT_GRANTED"


def test_superseded_full_pgn_policy_cannot_be_reactivated(mapping: dict[str, object]) -> None:
    reactivated = copy.deepcopy(mapping)
    policy = value(reactivated, "D20R2-016")["diagnostic_logging"]
    assert isinstance(policy, dict)
    policy["full_pgn"] = "ALLOWED_24_HOURS"
    with pytest.raises(DecisionValidationError, match="metadata-only"):
        validate_mapping(reactivated)

    accepted_again = copy.deepcopy(mapping)
    risk(accepted_again, "R4-005")["disposition"] = "ACCEPT"
    risk(accepted_again, "R4-005")["state"] = "ACTIVE"
    with pytest.raises(DecisionValidationError, match="R4-005"):
        validate_mapping(accepted_again)


def test_unknown_duplicate_secret_and_launch_mutations_fail_or_are_detected(
    mapping: dict[str, object],
) -> None:
    unknown = copy.deepcopy(mapping)
    unknown["unexpected"] = True
    with pytest.raises(DecisionValidationError, match="unknown"):
        validate_mapping(unknown)
    duplicate = copy.deepcopy(mapping)
    decisions(duplicate).append(copy.deepcopy(decisions(duplicate)[0]))
    with pytest.raises(DecisionValidationError, match="duplicate/conflicting"):
        validate_mapping(duplicate)
    launch = copy.deepcopy(mapping)
    launch["closed_pilot_launch_approved"] = True
    with pytest.raises(DecisionValidationError, match="must remain false"):
        validate_mapping(launch)
    serialized = json.dumps(mapping, sort_keys=True).lower()
    assert all(
        marker not in serialized
        for marker in ("private key-----", "token_value", "password_value", "sk-")
    )
    with pytest.raises(DecisionValidationError, match="exactly one"):
        load_single_mapping([MAPPING, MAPPING])
