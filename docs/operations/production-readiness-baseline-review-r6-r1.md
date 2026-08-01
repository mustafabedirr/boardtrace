# BoardTrace R6-R1 Staged Baseline Review

## 1. Identity and scope

- Objective: review and freeze the staged R3–R6 Mode-A repository baseline
  before any external provisioning.
- RUN_ID: `bt20dr6r1-20260801T133427-23d1973`
- Evidence identity: `boardtrace-readiness-baseline-r6-r1-23d1973`
- Repository revision: `23d19730e97dd0aa1503202cf3ce04a56f4ff776`
- Branch: `main`
- Commit/tag/push: `NO / NO / NO`
- MODE B authorization/execution: `NO / NO`
- External/production mutations: `0 / 0`

## 2. Git-state inventory and isolation

The reported starting 105-file index is confirmed: 78 added and 27 modified
files, 10,521 insertions and 108 deletions. Exported-index validation found
that the staged R6 qualification harness directly names tests in three omitted
files. Those production-readiness test files were selectively added. Together
with five R6-R1 evidence/generator artifacts, the final candidate contains 113
files. The machine-readable file-by-file review is
`production-readiness-staged-inventory-r6-r1.json`.

Before R6-R1 evidence is added, the working tree contains 44 tracked unstaged
paths, 105 untracked paths, and three mixed paths. Exported-index validation
then proved one staged logging assertion depended on the explicitly excluded
middleware `outcome` hunk. That assertion was selectively removed from the
index but preserved in the worktree, producing the reviewed final boundary of
42 tracked unstaged paths and four mixed paths after the three direct harness
dependencies were added. Every path and classification is recorded in the
inventory. Untracked application/docs work is treated as unrelated user work;
`apps/extension/build/` is generated work. Nothing was discarded, broadly
staged, or reset.

Mixed boundaries were reviewed independently:

- `apps/api/src/boardtrace_api/core/middleware.py`: staged request-ID
  unsafe-content validation belongs to R6; the independent request `outcome`
  log field remains unstaged.
- `apps/api/tests/test_logging.py`: the staged security/logging suite remains;
  only the assertion that requires the unstaged request `outcome` field is
  likewise unstaged, preserving a coherent index snapshot.
- `infrastructure/production-like/Dockerfile.api`: the complete safe non-root
  image is staged; the unstaged change only reorders `COPY scripts` after the
  package install and remains excluded.
- `scripts/validate_integrated_admission_lifecycle.py`: the complete R5-R2
  lifecycle harness is staged; the unstaged change replaces one direct status
  assertion with the shared `_expect` helper and remains excluded.

There is no context overlap in these boundaries. Validation from an exported
index snapshot is used so unstaged hunks cannot supply the reviewed result.

The three newly included dependencies are
`apps/api/tests/test_errors.py`, `apps/api/tests/test_settings.py`, and
`apps/api/tests/integration/test_transaction_boundary_ingestion.py`. Their
diffs are limited to the production failure-disclosure/configuration and
PostgreSQL concurrency tests explicitly executed by
`run_r6_evidence_qualification.ps1`.

## 3. Staged inventory result

The index contains authoritative decisions, risk/traceability records,
runtime lifecycle and queue code, logging safety, migration, extension
contract changes, Docker/backup/restore validation, production environment and
preflight gates, provisioning/SSH/operator artifacts, tests, and evidence.

- duplicate authoritative decision package: none; one Markdown and one JSON
  mapping with distinct roles;
- accidentally staged caches/logs/databases/coverage/secrets: none;
- generated runtime state: none;
- executable file modes: no unexpected executable-bit change;
- machine-specific runtime dependency: none; Windows paths are limited to
  documented local commands/historical evidence and are not production host
  configuration;
- placeholder use: explicit pending/not-provided/example values only;
- obsolete policies: retained only as clearly historical/superseded evidence.

## 4. Authoritative consistency

- mandatory identities: 28; resolved: 28; missing: 0; invalid: 0; conflicts: 0;
- active logging: metadata-only; raw PGN/FEN/moves/request body prohibited;
- full-PGN logging and password-only SSH: historical and superseded;
- SSH target: key-only TCP 48227, no password/root login, Fail2ban and rate
  limiting required;
- open blockers: R4-001, R4-007, R4-009;
- closed: R4-005 superseded, R4-010 verified, R4-011 verified;
- technical go: not passed; closed pilot: not yet granted; public launch: not
  granted; deployment and external provisioning: not performed.

No staged document claims a real host, DNS/TLS, R2, Telegram, GHCR credential,
Ahmet account, real production preflight, staffed drill, deployment, or launch.

## 5. Evidence chain and deterministic identity

R3 → R4 → R5 → R5-R1 → R5-R2 → R6 references exist and their run IDs are
internally consistent. Historical package/mapping hashes are intentionally not
presented as hashes of the later staged revisions; R4 and R5-R2 supersession
text makes the boundary explicit. No broken or circular evidence reference was
found.

`production-readiness-baseline-manifest-r6-r1.json` records the chain, current
critical SHA-256 values, Git HEAD, branch, inventory hash, and a deterministic
candidate-content identity. The self-referential inventory and manifest are
listed but excluded from that content identity; the algorithm is documented in
the manifest.

## 6. Security and privacy review

- secret/private-key/token/credential scan: no unapproved value;
- raw-game scan: matches are confined to synthetic minimal test fixtures and
  policy text; no real or unexplained reconstructable game record;
- personal data: accountable Mustafa/Ahmet names, synthetic `example.test`
  emails, documentation-only reserved example IPs; no phone/cookie/session;
- public exposure: only TCP 80/443/48227; PostgreSQL, Redis, worker, MinIO,
  Docker daemon, Dozzle and Uptime Kuma remain private/local-only;
- unsafe config: no wildcard production CORS, TLS-disable flag, password/root
  SSH, raw-game logging, debug production mode, or preflight bypass;
- live-game invariant: engine output remains server-side and locked until
  `ANALYSIS_AVAILABLE`.

## 7. Validation record

All commands run from `C:\boardtrace` unless an exported staged-snapshot path
is explicitly reported. Environment overrides use only ignored repository/temp
paths and synthetic loopback credentials.

| Command | Exit | Result |
| --- | ---: | --- |
| `python scripts/validate_production_decisions.py --require-decision-complete <mapping>` | 0 | 28/28; invalid/conflict 0 |
| `python scripts/validate_host_hardening.py` | 0 | staged SSH artifacts PASS |
| `python scripts/validate_provisioning_manifest.py` | 0 | Mode A; mutation count 0 |
| `ruff format --check .` / `ruff check .` / `mypy .` | 0/0/0 | clean |
| focused production/security pytest | 0 | 108 PASS |
| `scripts/run_r6_evidence_qualification.ps1` | 0 | 10 temp + 5 PostgreSQL PASS |
| staged-snapshot `tsc --noEmit` / Vitest | 0/0 | TypeScript PASS; 2 files / 7 tests PASS |
| focused staged JS/TS ESLint / focused Prettier | 0/0 | no staged-scope errors |
| global `pnpm lint` | 1 | 22 known errors in excluded unstaged/untracked web work; not PASS |
| Compose, shell, sudoers, OpenSSH, Caddy parsers | 0 | PASS; Caddy rerun with required synthetic ACME email after an incomplete first invocation |
| `run_production_like_validation.ps1 -RunId bt20dr6r1-20260801T133427-23d1973` | 0 | 117.6 s; lifecycle/Redis/backup/restore/teardown PASS |
| staged secret/raw-game/unsafe-config/diff scans | 0 | PASS with documented synthetic matches |

The staged snapshot contains only the two staged Vitest files (seven tests); the
larger worktree-only test suite is intentionally excluded from this baseline.
The first two final-snapshot pytest invocations produced 19 fixture setup
errors because the sandbox could not use the default user Temp directory and
the first repository-local `--basetemp` parent did not yet exist. After
creating that ignored parent, the identical test selection passed 108/108.
These were harness-environment corrections, not test or product-code changes.
No required failure or skip is hidden.

## 8. Global ESLint baseline

Global ESLint remains exit 1 with 22 errors in six excluded web paths plus one
excluded web validation script. Focused ESLint over staged JavaScript and
TypeScript files reports zero errors. Newly introduced staged-scope errors: 0.
The 22-error debt is not reclassified as PASS and is not expanded into R6-R1.

## 9. Commit boundary and identity

Recommendation: one atomic commit. Runtime imports, migration, decision-policy
supersession, Docker harness, validators, tests, and evidence were developed as
one staged chain. Splitting the accumulated R3–R6 index now would require
reconstructing and validating several intermediate trees and risks a transient
full-PGN policy, missing migration, or broken lifecycle import.

- exact file set: every path in
  `production-readiness-staged-inventory-r6-r1.json`;
- proposed message: `feat(production): establish reviewed mode-a readiness baseline`;
- body: record 28/28 decisions, metadata-only lifecycle controls, recovery
  validation, provisioning dry-run contracts, and keep external deployment
  blocked;
- proposed baseline name: `boardtrace-production-readiness-r6-mode-a`;
- optional annotated tag: `production-readiness/r6-mode-a-baseline`;
- tag message: `Reviewed Mode-A baseline; external provisioning and deployment remain blocked.`

No commit or tag is created by R6-R1.

## 10. Commit-ready and risk status

Final validation result:
`COMMIT_READY_WITH_BASELINE_DEBT`—the only repository-wide debt is the known 22
ESLint errors outside the staged candidate.

| Axis / risk | State |
| --- | --- |
| Decision package completeness | PASS |
| Runtime-policy alignment | PASS |
| Evidence-chain integrity | PASS |
| Staged-scope integrity | PASS |
| Secret/sensitive-content review | PASS |
| Validation reproducibility | PASS |
| R4-001 | READY_FOR_HOST_VERIFICATION / BLOCKED |
| R4-007 | READY_FOR_PROVISIONING / BLOCKED |
| R4-009 | IMPLEMENTED_PENDING_REAL_VALUES / BLOCKED |
| R4-010 / R4-011 | CLOSED / VERIFIED |
| External provisioning / deployment executability | BLOCKED / BLOCKED |
| Technical go / closed pilot / public launch | NOT YET PASSED / NOT YET GRANTED / NOT GRANTED |
| Prompt 20-D release | BLOCKED |

## 11. Authorization boundary

The exact 12-step packet is
`production-mode-b-authorization-packet-r6-r1.md`. The next user decision must
be one of `AUTHORIZE_COMMIT_ONLY`, `AUTHORIZE_MODE_B_PLAN_STEP_<N>`,
`AUTHORIZE_MODE_B_ALL_LISTED_STEPS`, or `DO_NOT_AUTHORIZE`. Commit authorization
does not authorize MODE B; MODE B does not authorize deployment or launch.

## 12. Honest limitations

R6-R1 proves repository/index integrity, not real provider or host state. It
cannot close R4-001/R4-007/R4-009, prove prices, provision credentials, verify
external DNS/TLS/R2/GHCR/Telegram, perform a staffed drill, or grant technical
go/launch. Those remain explicitly blocked.
