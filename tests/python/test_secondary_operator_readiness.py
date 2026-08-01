from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs/operations/production-incident-recovery-runbook.md"
DRILL = ROOT / "docs/operations/production-recovery-drill-checklist.md"
RECOVERY = ROOT / "infrastructure/production/ssh/boardtrace-recovery"
SUDOERS = ROOT / "infrastructure/production/ssh/sudoers.d/boardtrace-secondary"


def test_runbook_covers_required_incident_and_recovery_boundaries() -> None:
    text = RUNBOOK.read_text(encoding="utf-8").lower()
    for required in (
        "sev-1",
        "sev-2",
        "sev-3",
        "mustafa bedir",
        "ahmet bedir",
        "unreachable",
        "stop",
        "restart",
        "previous-known-good",
        "rollback",
        "health",
        "redis",
        "disk",
        "backup",
        "restore",
        "evidence",
        "escalate",
    ):
        assert required in text


def test_secondary_operator_allowlist_excludes_policy_and_deployment_actions() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    sudoers = SUDOERS.read_text(encoding="utf-8")
    for allowed in ("status", "stop", "restart", "rollback", "health"):
        assert allowed in recovery
    for prohibited in ("deploy", "approve", "expand", "policy"):
        assert f'"{prohibited}"' not in recovery
    assert "NOPASSWD: ALL" not in sudoers
    assert "boardtrace-recovery" in sudoers


def test_drill_template_has_scenarios_and_evidence_fields() -> None:
    text = DRILL.read_text(encoding="utf-8").lower()
    for scenario in (
        "stopped api container",
        "failed worker",
        "redis unavailable",
        "previous-known-good image",
        "disk threshold",
        "health:",
        "handoff",
    ):
        assert scenario in text
    for field in (
        "date",
        "participants",
        "initial state",
        "commands/actions",
        "observed result",
        "elapsed time",
        "success criteria",
        "deviations",
        "follow-up actions",
        "approvals",
    ):
        assert field in text
