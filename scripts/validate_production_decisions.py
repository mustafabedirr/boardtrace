"""Fail-closed validation for the authoritative BoardTrace production decisions."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

EXPECTED_DECISION_IDS: Final[tuple[str, ...]] = tuple(
    f"D20R2-{number:03d}" for number in range(1, 29)
)
SIGN_OFF_IDS: Final[tuple[str, ...]] = tuple(f"D20R2-{number:03d}" for number in range(20, 28))
EXPECTED_RISK_IDS: Final[tuple[str, ...]] = tuple(f"R4-{number:03d}" for number in range(1, 12))
ALLOWED_STATUSES: Final = {"DECIDED", "PENDING_PROVISIONING", "MISSING_DECISION", "NOT_APPLICABLE"}
ALLOWED_PROVISIONING_STATUSES: Final = {"NOT_REQUIRED", "PENDING", "NOT_PROVISIONED"}
ALLOWED_RISK_DISPOSITIONS: Final = {"ACCEPT", "MITIGATE", "AVOID", "TRANSFER", "EXPIRED", "CLOSED"}
ROOT_FIELDS: Final = {
    "schema_version",
    "document_version",
    "revision",
    "prior_version",
    "recorded_at",
    "source_document",
    "source_sha256",
    "integrated_source_path",
    "decision_owner",
    "environment_scope",
    "pilot_users",
    "invariant",
    "production_deployment_approved",
    "closed_pilot_launch_approved",
    "public_launch_approved",
    "independent_review_status",
    "decisions",
    "risks",
    "technical_blockers",
}
DECISION_FIELDS: Final = {
    "id",
    "title",
    "status",
    "value",
    "source_section",
    "decision_owner",
    "required_approver",
    "environment_scope",
    "provisioning_status",
    "notes",
}
RISK_FIELDS: Final = {
    "id",
    "title",
    "description",
    "scope",
    "owner",
    "disposition",
    "state",
    "controls",
    "recorded_at",
    "review",
    "expiry",
    "deployment_blocker",
    "implementation_evidence",
}


class DecisionValidationError(ValueError):
    """Raised when an authoritative decision mapping fails closed."""


@dataclass(frozen=True)
class ValidationSummary:
    mandatory_field_count: int
    resolved_field_count: int
    decided_field_count: int
    pending_provisioning_field_count: int
    missing_decision_field_count: int
    not_applicable_field_count: int
    invalid_field_count: int
    conflict_count: int
    sign_off_count: int
    active_accept_risk_count: int
    active_mitigate_risk_count: int
    expired_risk_count: int
    deployment_blocking_risk_count: int
    independent_review_status: str
    decision_completeness: str
    external_provisioning_completeness: str
    deployment_executability: str
    closed_pilot_launch_authorization: str
    public_launch_authorization: str
    technical_blockers: tuple[str, ...]


def _require_exact_fields(value: dict[str, object], allowed: set[str], label: str) -> None:
    missing = allowed - value.keys()
    unknown = value.keys() - allowed
    if missing or unknown:
        raise DecisionValidationError(
            f"{label} fields invalid; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionValidationError(f"{label} must be a non-empty string")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DecisionValidationError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise DecisionValidationError(f"{label} must be a list")
    return value


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DecisionValidationError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DecisionValidationError(f"{label} must include an offset")
    return text


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DecisionValidationError(f"{label} must be a positive integer")
    return value


def load_single_mapping(paths: list[Path]) -> dict[str, object]:
    if len(paths) != 1:
        raise DecisionValidationError("exactly one authoritative mapping is required")
    try:
        loaded = json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionValidationError(f"mapping could not be loaded: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DecisionValidationError("mapping root must be an object")
    return loaded


def _decision_by_id(mapping: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(item["id"]): item
        for item in _list(mapping["decisions"], "decisions")
        if isinstance(item, dict)
    }


def _validate_rate_limit(value: dict[str, object]) -> None:
    for field in ("authenticated_user_rpm", "global_authenticated_rpm", "health_ip_rpm"):
        _positive_int(value.get(field), f"D20R2-012.{field}")
    for prefix in ("analysis_start", "manual_retry", "failed_login"):
        _positive_int(value.get(f"{prefix}_limit"), f"D20R2-012.{prefix}_limit")
        _positive_int(value.get(f"{prefix}_window_minutes"), f"D20R2-012.{prefix}_window_minutes")
    _positive_int(value.get("failed_login_block_minutes"), "D20R2-012.failed_login_block_minutes")
    if value.get("anonymous_api") != "PROHIBITED_EXCEPT_MINIMUM_HEALTH":
        raise DecisionValidationError("D20R2-012 anonymous API policy is invalid")
    if value.get("health_exposes_metadata") is not False:
        raise DecisionValidationError("D20R2-012 /health metadata must be restricted")
    if value.get("state_backend") != "REDIS_SHARED":
        raise DecisionValidationError("D20R2-012 must use shared Redis-backed state")
    if value.get("redis_failure") != "FAIL_CLOSED":
        raise DecisionValidationError("D20R2-012 fail-open Redis behavior is prohibited")
    if value.get("rate_limit_status") != 429 or value.get("retry_after_required") is not True:
        raise DecisionValidationError("D20R2-012 HTTP 429 requires Retry-After")
    if value.get("redis_unavailable_status") != 503 or value.get("redis_retry_after_seconds") != 60:
        raise DecisionValidationError("D20R2-012 Redis failure requires 503 and Retry-After: 60")
    if value.get("log_retention_days") != 7 or value.get("masked_log_identity") is not True:
        raise DecisionValidationError("D20R2-012 requires masked seven-day violation logs")


def _validate_on_call(value: dict[str, object]) -> None:
    if (
        value.get("primary_on_call") != "Mustafa Bedir"
        or value.get("incident_commander") != "Mustafa Bedir"
    ):
        raise DecisionValidationError("D20R2-014 primary roles are unresolved")
    if (
        value.get("secondary_on_call") != "Ahmet Bedir"
        or value.get("secondary_trigger") != "PRIMARY_UNREACHABLE"
    ):
        raise DecisionValidationError("D20R2-014 secondary role is unresolved")
    allowed = {
        "STOP_SERVICE",
        "RESTART_CONTAINERS",
        "ROLLBACK_KNOWN_GOOD_IMAGE",
        "BASIC_DOCUMENTED_RECOVERY",
    }
    forbidden = {
        "ARCHITECTURE_CHANGE",
        "NEW_RELEASE",
        "PUBLIC_LAUNCH",
        "RISK_ACCEPTANCE",
        "PILOT_EXPANSION",
        "POLICY_CHANGE",
    }
    if set(_list(value.get("secondary_allowed_actions"), "secondary actions")) != allowed:
        raise DecisionValidationError("D20R2-014 secondary action scope is invalid")
    if (
        set(_list(value.get("secondary_forbidden_actions"), "secondary forbidden actions"))
        != forbidden
    ):
        raise DecisionValidationError("D20R2-014 forbidden secondary authorities are incomplete")
    if value.get("severity_response_minutes") != {"SEV-1": 15, "SEV-2": 60, "SEV-3": 1440}:
        raise DecisionValidationError("D20R2-014 severity response targets are invalid")
    if value.get("sev1_fail_closed") is not True or value.get("post_incident_review") != {
        "SEV-1": "MANDATORY",
        "SEV-2": "MANDATORY",
        "SEV-3": "OPTIONAL",
    }:
        raise DecisionValidationError("D20R2-014 incident review/fail-closed policy is incomplete")


def _validate_policies(decisions: dict[str, dict[str, object]]) -> None:
    _validate_rate_limit(_object(decisions["D20R2-012"]["value"], "D20R2-012.value"))
    _validate_on_call(_object(decisions["D20R2-014"]["value"], "D20R2-014.value"))
    pitr = _object(decisions["D20R2-015"]["value"], "D20R2-015.value")
    if (
        pitr.get("pitr") != "DISABLED_FOR_CLOSED_PILOT"
        or pitr.get("rpo_hours") != 24
        or not pitr.get("reassessment_triggers")
    ):
        raise DecisionValidationError("D20R2-015 explicit pilot PITR decision is incomplete")
    privacy = _object(decisions["D20R2-016"]["value"], "D20R2-016.value")
    required_privacy = {
        "data_minimization": True,
        "deletion_deadline_days": 30,
        "security_log_retention_days": 7,
        "sharing": "LEGAL_NECESSITY_ONLY",
        "request_channel": "BOARDTRACE_PILOT_TELEGRAM_INITIATION_PRIVATE_FOLLOWUP",
        "identity_verification": "REGISTERED_EMAIL_LINK_OR_CODE",
        "privacy_notice_before_processing": True,
    }
    if any(privacy.get(key) != expected for key, expected in required_privacy.items()):
        raise DecisionValidationError("D20R2-016 privacy policy is incomplete")
    diagnostic = _object(privacy.get("diagnostic_logging"), "D20R2-016.diagnostic_logging")
    required_logging = {
        "active_policy": "METADATA_ONLY",
        "supersedes": "R4_FULL_PGN_24_HOUR_LOGGING",
        "full_pgn": "PROHIBITED",
        "fen": "PROHIBITED",
        "raw_move_lists": "PROHIBITED",
        "game_request_bodies": "PROHIBITED",
        "reconstructable_engine_io": "PROHIBITED",
        "arbitrary_payload_fields": "PROHIBITED",
        "dozzle_access": "SSH_TUNNEL_ONLY_GENERAL_LOGS",
    }
    if diagnostic != required_logging:
        raise DecisionValidationError("D20R2-016 metadata-only logging policy is invalid")
    provenance = _object(decisions["D20R2-017"]["value"], "D20R2-017.value")
    if (
        provenance.get("temporary_fields")
        != ["source_platform", "source_game_id", "acquisition_method", "checksum"]
        or provenance.get("delete_at_terminal_state") is not True
        or provenance.get("source_mismatch") != "FAIL_CLOSED"
        or provenance.get("allowlist") != "VERSION_CONTROLLED_CODE_REVIEWED_CI_TESTED"
        or provenance.get("runtime_mutable_allowlist") is not False
        or provenance.get("error_log_retention_days") != 7
    ):
        raise DecisionValidationError("D20R2-017 provenance policy is incomplete")
    hash_policy = _object(provenance.get("diagnostic_game_hash"), "D20R2-017.diagnostic_game_hash")
    if hash_policy != {
        "canonical_representation_required": True,
        "operational_retention_only": True,
        "analysis_history": False,
        "permanent_user_profile": False,
        "raw_game_reconstruction": False,
    }:
        raise DecisionValidationError("D20R2-017 diagnostic hash policy is invalid")
    comms = _object(decisions["D20R2-018"]["value"], "D20R2-018.value")
    if (
        comms.get("initial_notice_minutes") != {"SEV-1": 30, "SEV-2": 120}
        or comms.get("update_minutes") != {"SEV-1": 60, "SEV-2": 240}
        or comms.get("planned_maintenance_notice_hours") != 24
        or comms.get("emergency_maintenance_without_notice") is not True
        or len(_list(comms.get("closure_fields"), "D20R2-018.closure_fields")) != 5
        or comms.get("restricted_security_disclosure") is not True
    ):
        raise DecisionValidationError("D20R2-018 communication policy is incomplete")
    launch = _object(decisions["D20R2-019"]["value"], "D20R2-019.value")
    if (
        launch.get("window")
        != "FIRST_SUNDAY_AFTER_ALL_TECHNICAL_GO_NO_GO_CHECKS_PASS_02:00-04:00_UTC+03:00"
        or launch.get("grants_launch_authorization") is not False
        or launch.get("public_launch") != "NOT_GRANTED"
    ):
        raise DecisionValidationError("D20R2-019 launch-window separation is invalid")


def _validate_signoffs(decisions: dict[str, dict[str, object]]) -> int:
    roles: set[str] = set()
    for decision_id in SIGN_OFF_IDS:
        value = _object(decisions[decision_id]["value"], f"{decision_id}.value")
        role = _text(value.get("role"), f"{decision_id}.role")
        if role in roles:
            raise DecisionValidationError("sign-off roles must remain distinct")
        roles.add(role)
        if (
            value.get("accountable_person") != "Mustafa Bedir"
            or value.get("approval") != "APPROVED"
        ):
            raise DecisionValidationError(f"{decision_id} sign-off is incomplete")
        if not _list(value.get("scope"), f"{decision_id}.scope"):
            raise DecisionValidationError(f"{decision_id} scope is empty")
        _timestamp(value.get("recorded_at"), f"{decision_id}.recorded_at")
        if (
            value.get("independent_review") != "ABSENT"
            or value.get("role_concentration_risk") != "R4-003"
        ):
            raise DecisionValidationError(f"{decision_id} independence disclosure is invalid")
    return len(roles)


def _validate_risks(raw_risks: object) -> tuple[int, int, int, int]:
    risks = _list(raw_risks, "risks")
    seen: set[str] = set()
    accept = mitigate = expired = blockers = 0
    for index, raw in enumerate(risks):
        risk = _object(raw, f"risk[{index}]")
        _require_exact_fields(risk, RISK_FIELDS, f"risk[{index}]")
        risk_id = _text(risk["id"], f"risk[{index}].id")
        if risk_id not in EXPECTED_RISK_IDS or risk_id in seen:
            raise DecisionValidationError(f"unknown or duplicate risk id: {risk_id}")
        seen.add(risk_id)
        for field in ("title", "description", "scope", "owner", "state", "review", "expiry"):
            _text(risk[field], f"{risk_id}.{field}")
        _timestamp(risk["recorded_at"], f"{risk_id}.recorded_at")
        if not _list(risk["controls"], f"{risk_id}.controls"):
            raise DecisionValidationError(f"{risk_id} controls/mitigation must not be empty")
        evidence = _list(risk["implementation_evidence"], f"{risk_id}.implementation_evidence")
        disposition = _text(risk["disposition"], f"{risk_id}.disposition")
        if disposition not in ALLOWED_RISK_DISPOSITIONS:
            raise DecisionValidationError(f"{risk_id} disposition is invalid")
        if disposition == "ACCEPT":
            accept += 1
            if risk["owner"] != "Mustafa Bedir" or risk["state"] != "ACTIVE":
                raise DecisionValidationError(f"{risk_id} acceptance is not active/accountable")
        elif disposition == "MITIGATE":
            mitigate += 1
            if risk["state"] != "OPEN" or risk["deployment_blocker"] is not True:
                raise DecisionValidationError(f"{risk_id} mitigation must remain a blocker")
            if evidence:
                raise DecisionValidationError(
                    f"{risk_id} mitigation cannot claim R4 implementation evidence"
                )
        elif disposition == "EXPIRED":
            expired += 1
            if risk["deployment_blocker"] is not True:
                raise DecisionValidationError(f"{risk_id} expired risk must fail safely")
        if risk["deployment_blocker"] is True:
            blockers += 1
    if seen != set(EXPECTED_RISK_IDS):
        raise DecisionValidationError(
            f"risk register incomplete; missing={sorted(set(EXPECTED_RISK_IDS) - seen)}"
        )
    full_pgn = next(risk for risk in risks if isinstance(risk, dict) and risk.get("id") == "R4-005")
    if (
        full_pgn.get("disposition") != "CLOSED"
        or full_pgn.get("state") != "SUPERSEDED"
        or full_pgn.get("deployment_blocker") is not False
    ):
        raise DecisionValidationError("R4-005 full-PGN policy must remain closed and superseded")
    for risk_id in ("R4-010", "R4-011"):
        verified = next(
            risk for risk in risks if isinstance(risk, dict) and risk.get("id") == risk_id
        )
        if (
            verified.get("disposition") != "CLOSED"
            or verified.get("state") != "VERIFIED"
            or verified.get("deployment_blocker") is not False
            or not verified.get("implementation_evidence")
        ):
            raise DecisionValidationError(
                f"{risk_id} must remain closed with verified implementation evidence"
            )
    return accept, mitigate, expired, blockers


def validate_mapping(mapping: dict[str, object]) -> ValidationSummary:
    _require_exact_fields(mapping, ROOT_FIELDS, "mapping")
    if mapping["schema_version"] != "boardtrace-production-decision-intake/v2":
        raise DecisionValidationError("unsupported schema_version")
    if mapping["document_version"] != "v1.0-pilot" or mapping["revision"] != "R5-R2":
        raise DecisionValidationError("unsupported document revision")
    if mapping["prior_version"] != "v1.0-pilot/R4":
        raise DecisionValidationError("prior_version must preserve R4 provenance")
    _timestamp(mapping["recorded_at"], "recorded_at")
    for field in ("source_document", "integrated_source_path", "decision_owner"):
        _text(mapping[field], field)
    source_hash = _text(mapping["source_sha256"], "source_sha256")
    if len(source_hash) != 64 or any(
        character not in "0123456789abcdef" for character in source_hash
    ):
        raise DecisionValidationError("source_sha256 must be lowercase SHA-256")
    if mapping["environment_scope"] != "closed_production_pilot" or mapping["pilot_users"] != 5:
        raise DecisionValidationError("closed five-user pilot scope is required")
    if mapping["invariant"] != "NO ENGINE OUTPUT DURING LIVE GAMES":
        raise DecisionValidationError("live-game engine-output invariant must remain fail-closed")
    if mapping["independent_review_status"] != "ABSENT":
        raise DecisionValidationError("independent review must not be falsely asserted")
    for approval in (
        "production_deployment_approved",
        "closed_pilot_launch_approved",
        "public_launch_approved",
    ):
        if mapping[approval] is not False:
            raise DecisionValidationError(f"{approval} must remain false")

    decisions_raw = _list(mapping["decisions"], "decisions")
    seen: set[str] = set()
    counts = {status: 0 for status in ALLOWED_STATUSES}
    for index, raw in enumerate(decisions_raw):
        decision = _object(raw, f"decision[{index}]")
        _require_exact_fields(decision, DECISION_FIELDS, f"decision[{index}]")
        decision_id = _text(decision["id"], f"decision[{index}].id")
        if decision_id not in EXPECTED_DECISION_IDS or decision_id in seen:
            raise DecisionValidationError(
                f"unknown or duplicate/conflicting decision id: {decision_id}"
            )
        seen.add(decision_id)
        status = _text(decision["status"], f"{decision_id}.status")
        if status not in ALLOWED_STATUSES:
            raise DecisionValidationError(f"unsupported status for {decision_id}: {status}")
        counts[status] += 1
        for field in ("title", "source_section", "decision_owner", "required_approver", "notes"):
            _text(decision[field], f"{decision_id}.{field}")
        if decision["environment_scope"] != "closed_production_pilot":
            raise DecisionValidationError(f"{decision_id}.environment_scope is invalid")
        provisioning = _text(decision["provisioning_status"], f"{decision_id}.provisioning_status")
        if provisioning not in ALLOWED_PROVISIONING_STATUSES:
            raise DecisionValidationError(
                f"unsupported provisioning status for {decision_id}: {provisioning}"
            )
        if status == "MISSING_DECISION" and decision["value"] is not None:
            raise DecisionValidationError(f"{decision_id} missing decision must have null value")
        if status != "MISSING_DECISION" and decision["value"] is None:
            raise DecisionValidationError(f"{decision_id} resolved decision must have a value")
        if status == "PENDING_PROVISIONING" and provisioning != "PENDING":
            raise DecisionValidationError(f"{decision_id} pending provisioning must use PENDING")
    if seen != set(EXPECTED_DECISION_IDS):
        missing_decisions = sorted(set(EXPECTED_DECISION_IDS) - seen)
        raise DecisionValidationError(
            f"mandatory decision IDs incomplete; missing={missing_decisions}"
        )

    indexed = _decision_by_id(mapping)
    _validate_policies(indexed)
    sign_off_count = _validate_signoffs(indexed)
    risk_ids = _object(indexed["D20R2-028"]["value"], "D20R2-028.value").get("risk_ids")
    if risk_ids != list(EXPECTED_RISK_IDS):
        raise DecisionValidationError("D20R2-028 must link the complete ordered risk register")
    accept, mitigate, expired, risk_blockers = _validate_risks(mapping["risks"])
    blockers = _list(mapping["technical_blockers"], "technical_blockers")
    if not blockers or not all(
        isinstance(blocker, str) and blocker.strip() for blocker in blockers
    ):
        raise DecisionValidationError("technical_blockers must contain non-empty blockers")

    resolved = counts["DECIDED"] + counts["PENDING_PROVISIONING"] + counts["NOT_APPLICABLE"]
    decision_completeness = "PASS" if resolved == 28 else "BLOCKED"
    provisioning = "PASS" if counts["PENDING_PROVISIONING"] == 0 else "BLOCKED"
    executable = (
        "READY"
        if decision_completeness == "PASS"
        and provisioning == "PASS"
        and not blockers
        and risk_blockers == 0
        else "BLOCKED"
    )
    return ValidationSummary(
        28,
        resolved,
        counts["DECIDED"],
        counts["PENDING_PROVISIONING"],
        counts["MISSING_DECISION"],
        counts["NOT_APPLICABLE"],
        0,
        0,
        sign_off_count,
        accept,
        mitigate,
        expired,
        risk_blockers,
        str(mapping["independent_review_status"]),
        decision_completeness,
        provisioning,
        executable,
        "GRANTED"
        if mapping["closed_pilot_launch_approved"] is True and executable == "READY"
        else "NOT_YET_GRANTED",
        "GRANTED"
        if mapping["public_launch_approved"] is True and executable == "READY"
        else "NOT_GRANTED",
        tuple(str(blocker) for blocker in blockers),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapping", nargs="+", type=Path)
    parser.add_argument("--require-decision-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = validate_mapping(load_single_mapping(args.mapping))
    except DecisionValidationError as exc:
        print(json.dumps({"validation": "FAILED", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"validation": "PASSED", **asdict(summary)}, sort_keys=True))
    if args.require_decision_complete and summary.decision_completeness != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
