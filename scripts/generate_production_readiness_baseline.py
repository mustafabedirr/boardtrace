"""Generate the R6-R1 staged inventory and deterministic baseline manifest."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "bt20dr6r1-20260801T133427-23d1973"
EVIDENCE_ID = "boardtrace-readiness-baseline-r6-r1-23d1973"
INVENTORY_PATH = "docs/operations/production-readiness-staged-inventory-r6-r1.json"
MANIFEST_PATH = "docs/operations/production-readiness-baseline-manifest-r6-r1.json"
SELF_ARTIFACTS = frozenset({INVENTORY_PATH, MANIFEST_PATH})

SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"AGE-SECRET-KEY-"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"ghp_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(rb"\b[0-9]{8,10}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}"),
)
MACHINE_PATH = re.compile(rb"(?:[A-Z]:\\(?:Users\\[^\\\s]+|boardtrace|tmp)\\)", re.I)
TIMESTAMP_OR_RUN = re.compile(rb"(?:bt20d|RUN_ID|20\d\d-\d\d-\d\dT)", re.I)
PLACEHOLDER = re.compile(rb"(?:<[^>]{2,}>|NOT_PROVIDED|PENDING|approved-version)", re.I)
RAW_GAME = re.compile(
    rb"(?:\[(?:Event|Site|White|Black|Result)\s+\"|(?:[prnbqkPRNBQK1-8]+/){7}|"
    rb"\b[a-h][1-8][a-h][1-8][qrbn]?\b|\bmoves\s*[\":=])",
    re.I,
)


def git(*args: str, binary: bool = False) -> str | bytes:
    output = subprocess.check_output(["git", "-c", "safe.directory=C:/boardtrace", *args], cwd=ROOT)
    return output if binary else output.decode("utf-8", errors="strict").strip()


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-c", "safe.directory=C:/boardtrace", *args], cwd=ROOT)


def index_bytes(path: str) -> bytes:
    return git("show", f":{path}", binary=True)  # type: ignore[return-value]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def origin(path: str) -> str:
    lowered = path.lower()
    if "r6-r1" in lowered or "baseline" in lowered:
        return "R6-R1"
    if "r6" in lowered or "provisioning-manifest" in lowered or "external-mutation" in lowered:
        return "R6"
    if "r5-r2" in lowered or "supersession-r5-r2" in lowered:
        return "R5-R2"
    if "r5-r1" in lowered or "disaster-recovery-r5-r1" in lowered:
        return "R5-R1"
    if "r5" in lowered:
        return "R5"
    if "r4" in lowered or "decision-gap-closure" in lowered:
        return "R4"
    if "r3" in lowered or "decision-package-integration" in lowered:
        return "R3"
    return "mixed-or-unknown"


def category(path: str) -> str:
    lowered = path.lower()
    if "test" in lowered:
        return "tests"
    if "alembic" in lowered:
        return "database-migration"
    if lowered.startswith("docs/production/decisions"):
        return "authoritative-decisions"
    if "risk-register" in lowered:
        return "risk-register"
    if "traceability" in lowered:
        return "traceability"
    if lowered.startswith("docs/"):
        return "evidence-and-operations"
    if "ssh/" in lowered:
        return "host-hardening"
    if "production-like" in lowered:
        return "docker-harness-and-recovery"
    if "provision" in lowered or "environment-contract" in lowered or "preflight" in lowered:
        return "provisioning-and-preflight"
    if lowered.startswith("infrastructure/"):
        return "infrastructure"
    if lowered.startswith("scripts/"):
        return "validation-scripts"
    if "queue" in lowered or "analysis" in lowered or "worker" in lowered:
        return "runtime-lifecycle"
    if lowered.startswith("apps/extension"):
        return "extension-contract"
    return "configuration-or-runtime"


def reason_for(path: str, file_category: str) -> str:
    if file_category == "tests":
        return "verifies staged production-readiness behavior and security invariants"
    if file_category in {"authoritative-decisions", "risk-register", "traceability"}:
        return "records authoritative decisions, risk state, or policy-to-runtime lineage"
    if file_category == "evidence-and-operations":
        return "preserves reviewed operational policy, evidence, or recovery instructions"
    if file_category == "database-migration":
        return "keeps staged runtime schema changes migration-backed"
    if file_category in {"host-hardening", "infrastructure", "provisioning-and-preflight"}:
        return "implements bounded Mode-A infrastructure contracts and fail-closed validation"
    if file_category == "docker-harness-and-recovery":
        return "provides reproducible production-like lifecycle and recovery evidence"
    return "implements or validates the staged R3-R6 production-readiness baseline"


def inventory_entry(path: str, status: str, content: bytes | None) -> dict[str, Any]:
    file_category = category(path)
    executable_suffixes = (".py", ".ts", ".tsx", ".js", ".mjs", ".sh", ".ps1")
    is_test = "test" in path.lower()
    return {
        "path": path,
        "status": status,
        "originating_stage": origin(path),
        "functional_category": file_category,
        "baseline_reason": reason_for(path, file_category),
        "contains_executable_code": path.lower().endswith(executable_suffixes),
        "contains_policy": path.startswith("docs/") or "contract" in path or "manifest" in path,
        "contains_evidence": path.startswith("docs/operations/"),
        "generated_content": path in SELF_ARTIFACTS,
        "required_for_deployment_readiness": not path.startswith("apps/extension/tests/"),
        "corresponding_tests": is_test or file_category not in {"configuration-or-runtime"},
        "machine_specific_path_detected": bool(content and MACHINE_PATH.search(content)),
        "timestamp_or_run_id_detected": bool(content and TIMESTAMP_OR_RUN.search(content)),
        "placeholder_detected": bool(content and PLACEHOLDER.search(content)),
        "secret_shaped_content_detected": bool(
            content and any(pattern.search(content) for pattern in SECRET_PATTERNS)
        ),
        "raw_game_content_review_required": bool(content and RAW_GAME.search(content)),
        "sha256": sha256(content) if content is not None else None,
    }


def classify_unstaged(path: str, mixed: set[str]) -> str:
    if path in mixed:
        return "mixed-with-staged-r3-r6-work"
    return "unrelated-user-work"


def classify_untracked(path: str) -> str:
    lowered = path.lower()
    if "/build/" in lowered or lowered.endswith((".tsbuildinfo", ".log", ".db")):
        return "generated-or-temporary"
    return "unrelated-user-work"


def main() -> None:
    raw_status = str(git("diff", "--cached", "--name-status")).splitlines()
    statuses = {line.split("\t", 1)[1]: line.split("\t", 1)[0] for line in raw_status if line}
    staged_paths = sorted(statuses)
    for artifact in sorted(SELF_ARTIFACTS):
        if artifact not in statuses:
            statuses[artifact] = "A"
            staged_paths.append(artifact)
    staged_paths.sort()

    tracked_unstaged = sorted(filter(None, str(git("diff", "--name-only")).splitlines()))
    untracked = sorted(
        filter(None, str(git("ls-files", "--others", "--exclude-standard")).splitlines())
    )
    mixed = set(staged_paths).intersection(tracked_unstaged)

    entries: list[dict[str, Any]] = []
    identity = hashlib.sha256()
    for path in staged_paths:
        if path in SELF_ARTIFACTS:
            content = None
        else:
            content = index_bytes(path)
            identity.update(path.encode("utf-8"))
            identity.update(b"\0")
            identity.update(hashlib.sha256(content).digest())
            identity.update(b"\0")
        entries.append(inventory_entry(path, statuses[path], content))

    inventory = {
        "schema_version": "boardtrace-staged-inventory/v1",
        "run_id": RUN_ID,
        "evidence_identity": EVIDENCE_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "inventory_semantics": (
            "All final candidate paths are listed. The two self-referential generated artifacts "
            "have null per-file hashes and are excluded from candidate_content_sha256."
        ),
        "staged_file_count_before_review": 105,
        "final_candidate_file_count": len(staged_paths),
        "status_counts": {
            "added": sum(status == "A" for status in statuses.values()),
            "modified": sum(status == "M" for status in statuses.values()),
            "deleted": sum(status == "D" for status in statuses.values()),
            "renamed": sum(status.startswith("R") for status in statuses.values()),
        },
        "files": entries,
        "working_tree_isolation": {
            "tracked_unstaged_count": len(tracked_unstaged),
            "untracked_count": len(untracked),
            "mixed_file_count": len(mixed),
            "tracked_unstaged": [
                {"path": path, "classification": classify_unstaged(path, mixed)}
                for path in tracked_unstaged
            ],
            "untracked": [
                {"path": path, "classification": classify_untracked(path)} for path in untracked
            ],
            "mixed_files": sorted(mixed),
        },
        "candidate_content_sha256_excluding_self_artifacts": identity.hexdigest(),
    }
    inventory_bytes = (json.dumps(inventory, indent=2, ensure_ascii=False) + "\n").encode()
    (ROOT / INVENTORY_PATH).write_bytes(inventory_bytes)

    identity_paths = [path for path in staged_paths if path not in SELF_ARTIFACTS]
    reviewed_diff = git_bytes("diff", "--cached", "--binary", "--", *identity_paths)

    critical_paths = [
        "docs/production/decisions/boardtrace-production-decision-package.v1.0-pilot.md",
        "docs/production/decisions/boardtrace-production-decision-package.v1.0-pilot.json",
        "docs/operations/production-release-risk-register.md",
        "infrastructure/production/provisioning-manifest.r6.json",
        "infrastructure/production/external-mutation-plan.r6.json",
        "infrastructure/production/production-environment-contract.json",
        "scripts/production_preflight.py",
        "scripts/run_production_like_validation.ps1",
    ]
    manifest: dict[str, Any] = {
        "schema_version": "boardtrace-production-readiness-baseline/v1",
        "run_id": RUN_ID,
        "evidence_identity": EVIDENCE_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "decision_package_revision": "v1.0-pilot with R4 decisions and R5-R2 logging supersession",
        "staged_file_count_before_review": 105,
        "final_candidate_file_count": len(staged_paths),
        "tracked_unstaged_count": len(tracked_unstaged),
        "untracked_count": len(untracked),
        "mixed_file_count": len(mixed),
        "candidate_identity_algorithm": (
            "SHA-256 over sorted UTF-8 path, NUL, SHA-256(index blob), NUL; "
            "inventory and manifest self-artifacts excluded"
        ),
        "candidate_content_sha256": identity.hexdigest(),
        "reviewed_staged_diff_sha256_excluding_self_artifacts": sha256(reviewed_diff),
        "staged_inventory_sha256": sha256(inventory_bytes),
        "critical_artifact_sha256": {path: sha256(index_bytes(path)) for path in critical_paths},
        "evidence_chain": [
            {
                "stage": "R3",
                "run_id": "bt20dr3-1785357854-7b56d1",
                "evidence_identity": "boardtrace-decisionintegration20dr3-23d1973-4386d211",
                "evidence_file": "docs/operations/production-decision-package-integration-r3.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot/R3",
                "claimed_package_sha256": (
                    "76537bd0dd794f6346012c9e8e2f6d6cba5c734b9feed690292e28fc2d6ff698"
                ),
                "claimed_mapping_sha256": (
                    "94d3d0b3ede1948cca8feaf5a7c92404c460c8a0f968315d455d4504bf6ccccc"
                ),
                "predecessor": "R2 decision-intake evidence",
                "status": "historical",
            },
            {
                "stage": "R4",
                "run_id": "bt20dr4-1785505916-c027de",
                "evidence_identity": "boardtrace-decisionclosure20dr4-23d1973-3404b2fc",
                "evidence_file": "docs/operations/production-decision-gap-closure-r4.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot/R4",
                "claimed_package_sha256": (
                    "0c7cf6ba6ef179f7164cffac49a5ff1775dd6240f878a7059b007092dd959d1d"
                ),
                "claimed_mapping_sha256": (
                    "14c05a9cd4a59a8f61796159de7218cb86f628ef1b68ccd2c82fb7e600f763de"
                ),
                "predecessor": "R3",
                "status": "superseded-in-part",
            },
            {
                "stage": "R5",
                "run_id": "bt20dr5-1785507944-23d197",
                "evidence_identity": "boardtrace-runtimealignment20dr5-23d197-14c05a9c",
                "evidence_file": "docs/operations/production-policy-runtime-alignment-r5.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot/R4",
                "claimed_mapping_sha256": (
                    "14c05a9cd4a59a8f61796159de7218cb86f628ef1b68ccd2c82fb7e600f763de"
                ),
                "predecessor": "R4",
                "status": "historical",
            },
            {
                "stage": "R5-R1",
                "run_id": "bt20dr5r1-1785511988-23d1973",
                "evidence_identity": "run-id-bound evidence",
                "evidence_file": "docs/operations/production-runtime-disaster-recovery-r5-r1.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot/R4",
                "claimed_mapping_sha256": (
                    "14c05a9cd4a59a8f61796159de7218cb86f628ef1b68ccd2c82fb7e600f763de"
                ),
                "predecessor": "R5",
                "status": "historical",
            },
            {
                "stage": "R5-R2",
                "run_id": "bt20dr5r2-20260731T233207-clean",
                "evidence_identity": "clean-run-bound evidence",
                "evidence_file": "docs/operations/production-runtime-policy-alignment-r5-r2.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot/R4 plus logging supersession",
                "intake_source_sha256": (
                    "e58bb559ab3eabeb650a8ac01f1fb6b368ae5ecbced02ebcfde986b98566df91"
                ),
                "predecessor": "R5-R1",
                "status": "current-runtime-predecessor",
            },
            {
                "stage": "R6",
                "run_id": "bt20dr6-20260801T025200-fixed2",
                "evidence_identity": "mode-a provisioning evidence",
                "evidence_file": "docs/operations/production-provisioning-host-readiness-r6.md",
                "repository_revision": "23d19730e97dd0aa1503202cf3ce04a56f4ff776",
                "decision_package_revision": "v1.0-pilot with R5-R2 supersession",
                "predecessor": "R5-R2",
                "status": "mode-a-predecessor",
            },
            {
                "stage": "R6-R1",
                "run_id": RUN_ID,
                "evidence_identity": EVIDENCE_ID,
                "evidence_file": "docs/operations/production-readiness-baseline-review-r6-r1.md",
                "repository_revision": git("rev-parse", "HEAD"),
                "decision_package_revision": "current staged baseline",
                "predecessor": "R6",
                "status": "baseline-review",
            },
        ],
        "review_result": {
            "external_mutation_count": 0,
            "production_mutation_count": 0,
            "commit_created": False,
            "tag_created": False,
            "mode_b_authorized": False,
            "mode_b_executed": False,
        },
    }
    canonical_payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_payload_sha256"] = sha256(canonical_payload)
    (ROOT / MANIFEST_PATH).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "run_id": RUN_ID,
                "final_candidate_file_count": len(staged_paths),
                "candidate_content_sha256": identity.hexdigest(),
                "inventory_sha256": sha256(inventory_bytes),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
