# Prompt 20-D-R5 Production Policy Runtime Alignment Evidence

## 1. R5 summary

- RUN_ID: `bt20dr5-1785507944-23d197`
- Evidence identity: `boardtrace-runtimealignment20dr5-23d197-14c05a9c`
- Timestamp: `2026-07-31T17:25:41+03:00`
- Repository revision: `23d19730e97dd0aa1503202cf3ce04a56f4ff776`
- Authoritative package: `v1.0-pilot/R4`
- Decision-package JSON SHA-256: `14c05a9cd4a59a8f61796159de7218cb86f628ef1b68ccd2c82fb7e600f763de`
- R4 evidence: `bt20dr4-1785505916-c027de`
- Production/external mutation count: `0`

R5 implemented repository controls for SSH, secondary recovery, a no-bypass
environment gate, provenance, production rate limits, minimum health, disabled
automatic retry, terminal cleanup, and one-time result consumption. It did not
complete the bounded Redis queue, every terminal cleanup path, the isolated
24-hour PGN log, or current Docker integration validation. R5 and Prompt 20-D
therefore remain incomplete and blocked.

## 2. Repository inspection

The API is FastAPI with PostgreSQL/SQLAlchemy persistence. Completed-game
ingestion creates durable Game and AnalysisJob rows in an explicit service
transaction; an outbox publishes work to a Celery Redis queue. A backend worker
claims/leases the job, validates the completed-game input, invokes native
Stockfish, and persists an AnalysisRun/result generation. The web client polls
owner-scoped status/read endpoints. Before R5, ingestion auto-admitted work,
Celery retried retryable failures, results were historically retrievable, and
source provenance was not enforced by a canonical checksum.

No Dockerfile or Compose file existed at initial inspection. R5 subsequently
added an isolated production-like composition and a deterministic validation
harness. There is still no production deployment entry point; the harness
performs no deployment.

## 3. Risk implementation and verification

| Risk | Implementation | Current verification | State / deployment effect |
| --- | --- | --- | --- |
| R4-001 | hardened sshd drop-in, UFW/fail2ban install/rollback, key presence guard, validator | static validator and tests PASS | IMPLEMENTED_PENDING_HOST_VERIFICATION / BLOCKING |
| R4-007 | named-account design, allowlisted dispatcher, scoped sudoers, incident runbook and drill template | static readiness tests PASS | READY_FOR_PROVISIONING / BLOCKING until access and first drill |
| R4-009 | canonical environment contract and no-bypass chained preflight | safe complete fixture PASS; empty real environment correctly FAILS | REPOSITORY_IMPLEMENTED, EXTERNAL_PREFLIGHT_BLOCKED / BLOCKING |
| R4-010 | partial runtime alignment described in traceability document | focused backend/extension tests PASS for implemented slices | PARTIAL/BLOCKED |
| R4-011 | isolated API/worker/PostgreSQL/Redis/Caddy composition and teardown harness | current core composition PASS; full failure/backup suite incomplete | PARTIAL/BLOCKED |

Password-only SSH is superseded by the key-only target. R4-001 is not closed:
the actual Ubuntu 24.04 effective configuration, firewall and Fail2ban state
were not available for verification.

## 4. Runtime alignment details

- Session-only results: the first successful owner read maps the public payload,
  deletes the result generation, and prevents later retrieval. The extension
  warns that closing the session loses the result. Undelivered server results
  are not yet tied to browser-session termination, so this is partial.
- Deletion: success and accepted terminal failure clear submitted moves,
  position/frame data, source identifiers, acquisition checksum and provenance
  in the terminal transaction. Timeout, cancellation, retry exhaustion,
  queue-expiry and crash-recovery coverage is incomplete.
- Queue: existing outbox/Celery behavior does not provide explicit consent,
  bounded Redis FIFO, waiting cancellation, queue position, or 3+3-minute
  extension. This is the principal unresolved implementation blocker.
- Timeout/retry: production limits are 170-second soft and 180-second hard;
  automatic retry defaults off and production rejects enabling it. Manual retry
  is fingerprint-limited to two per 15 minutes. Late-result/timeout races remain
  incompletely verified.
- Rate limit: Redis-backed atomic counters enforce user/global/start/retry,
  login/IP and health limits, with 429/Retry-After and fail-closed
  503/Retry-After 60. Persistent seven-day violation-log retention and
  concurrent Redis evidence remain outstanding.
- Provenance: only the version-controlled `lichess` plus
  `browser_extension` path is accepted; canonical SHA-256 mismatch fails before
  ingestion. Unsupported/manual sources fail closed.
- PGN logging: ordinary logs continue to prohibit PGN/FEN/moves. The approved
  isolated full-PGN sink with enforced 24-hour deletion is not implemented.
- Live-game invariant: server-owned completion checks remain immediately before
  engine invocation. External-source revalidation after a queue wait and all
  required stale/late race tests are not complete; no invariant was weakened.

Detailed mappings are in
`docs/operations/production-runtime-policy-traceability-r5.md`.

## 5. Validation evidence

| Command | Exit | Result |
| --- | ---: | --- |
| `uv run pytest -q ...R5 focused backend/infrastructure files...` | 0 | 52 passed; pytest cache warning only |
| `uv run pytest -q` | 0 | 37 repository Python tests passed; pytest cache warning only |
| `uv run pytest -q apps/api/tests` | 1 then 0 | two production-test assumptions fixed; final 251 passed, 155 environment skips |
| `pnpm vitest run apps/extension/tests/protocol.test.ts apps/extension/tests/production-config.test.ts` | 0 | 11 passed |
| `pnpm --filter @boardtrace/extension typecheck` | 0 | passed |
| `uv run ruff format --check ...`; `uv run ruff check ...` | 0 after one import-order fix | focused R5 files clean |
| `uv run mypy apps/api/src/boardtrace_api` | 0 | 78 source files clean |
| `uv run python scripts/validate_production_decisions.py --require-decision-complete ...` | 0 | 28/28 decisions resolved; completeness PASS |
| `uv run python scripts/validate_host_hardening.py` | 0 | repository hardening artifacts PASS |
| `uv run python scripts/validate_production_environment.py` | 1 expected | missing real production keys named; no values printed |
| `uv run python scripts/production_preflight.py` | 1 | first run exposed/fixed import path; second run blocked at absent environment as designed |
| `docker info --format 'Server={{.ServerVersion}}; OSType={{.OSType}}; ContainersRunning={{.ContainersRunning}}'` | 1 then 0 | initial daemon pipe absent; rerun found Docker 29.6.1 Linux daemon |
| `docker compose -f infrastructure/production-like/compose.yaml config --quiet` | 0 | Compose schema/configuration PASS |
| `.\scripts\run_production_like_validation.ps1` | 1, 1, then 0 | corrupt ignore glob fixed; host/internal-network probe fixed; final core validation PASS |

Additional current gates: `uv run ruff format --check .` passed for 180 files;
`uv run ruff check .` and `uv run mypy .` passed. `pnpm typecheck` passed and
`pnpm test` passed 153 tests. Global `pnpm format:check` could not traverse the
pytest-created access-restricted `.tmp` tree. Global `pnpm lint` found 22
pre-existing errors in unstaged web files; focused Prettier/ESLint over the R5
extension/tooling files passed. The staged credential-pattern scan reported no
matches and `git diff --cached --check` passed after EOF whitespace repair.

The deterministic Docker rerun is
`.\scripts\run_production_like_validation.ps1`. The final run built test-only
images, migrated PostgreSQL to `f03a4b5c6d7e (head)`, observed PostgreSQL
accepting connections, Redis `PONG`, authenticated API-to-database readiness,
a Redis/Celery outbox probe completed by the worker, and healthy API, worker,
Caddy, PostgreSQL and Redis services. It then removed all containers, the
network and the test volume; follow-up resource queries returned empty. The API and worker image
identities were respectively `sha256:28cf9e04fc1d69a03940eb4c5574e8376a1d0bdab078b76587c8d12d536541c8`
and `sha256:7e4e380c4936d6d9133abb01e20dec7dccdae46794dafb44500d0171d3fb18db`.

This is core composition PASS, not full R4-011 closure: encrypted
backup/upload/restore and the complete runtime failure/queue suite did not run.

## 6. Status axes

| Axis | Status |
| --- | --- |
| Decision Package Completeness | PASS |
| SSH Mitigation Repository Implementation | PASS |
| SSH Production Host Verification | BLOCKED |
| Secondary Operator Readiness | READY_FOR_PROVISIONING / BLOCKED externally |
| Provisioning Gate Repository Implementation | PASS |
| External Provisioning Preflight | BLOCKED |
| Runtime Policy Alignment | PARTIAL / BLOCKED |
| Production-Like Docker Validation | CORE PASS / FULL SUITE BLOCKED |
| External Provisioning Completeness | BLOCKED |
| Deployment Executability | BLOCKED |
| Technical Go/No-Go | NOT YET PASSED |
| Closed Pilot Launch Authorization | NOT YET GRANTED |
| Public Launch Authorization | NOT GRANTED |
| Prompt 20-D-R5 Complete | NO |
| Prompt 20-D Release | BLOCKED |

## 7. Remaining blockers and limitations

- Implement and race-test explicit Redis queue consent, FIFO/capacity,
  cancellation, queue expiry and extension approval.
- Cover cleanup and late-result invalidation for timeout, cancellation,
  retry exhaustion, queue expiry and worker crash recovery.
- Implement a separately protected full-PGN technical log with enforced
  maximum 24-hour deletion, or obtain an authoritative policy revision; do not
  put raw PGN in ordinary logs.
- Extend the passing core Docker composition with the complete queue,
  timeout/cancellation/cleanup, Redis-failure, restart and encrypted
  backup/upload/restore suite.
- Provision and verify the real host, external values, Ahmet's access and first
  drill. Perform the technical go/no-go and later accountable launch decision.

No Hetzner, DuckDNS, TLS, Telegram, R2, GHCR, production host, public traffic,
or launch-authorization mutation occurred. No real secret was used. The Docker
build contacted Docker Hub for base images, Debian package mirrors for
Stockfish, and PyPI for declared Python dependencies; it contacted no
BoardTrace production or provisioned pilot system.

## 8. Files and Git state

Pre-change staged count was 22 R3/R4 files. Post-Docker-rerun staged count is
64: 42 paths were added to the index by R5, and the already-staged risk register
also received its R5 status addendum. No commit was created.

| Staged R5 path | Purpose |
| --- | --- |
| `.gitignore`; `.prettierignore`; `eslint.config.mjs` | exclude R5-local temporary test state from tooling |
| `infrastructure/production/production-environment-contract.json` | canonical required/optional production configuration |
| `infrastructure/production/ssh/boardtrace-recovery` | allowlisted secondary recovery dispatcher |
| `infrastructure/production/ssh/fail2ban/boardtrace-sshd.local` | SSH ban/rate policy |
| `infrastructure/production/ssh/install-host-hardening.sh` | guarded idempotent install and effective checks |
| `infrastructure/production/ssh/rollback-host-hardening.sh` | documented safe rollback artifact |
| `infrastructure/production/ssh/sshd_config.d/60-boardtrace-production.conf` | key-only port-48227 target |
| `infrastructure/production/ssh/sudoers.d/boardtrace-secondary` | least-privilege Ahmet command boundary |
| `scripts/validate_host_hardening.py` | static hardening validator |
| `scripts/validate_production_environment.py` | secret-safe no-bypass environment gate |
| `scripts/production_preflight.py` | chained decision/host/environment entry gate |
| `tests/python/test_host_hardening.py` | unsafe SSH target rejection tests |
| `tests/python/test_production_environment.py` | complete/missing/placeholder/no-disclosure gate tests |
| `tests/python/test_secondary_operator_readiness.py` | runbook, drill and dispatcher boundary tests |
| `docs/operations/production-deployment-preflight.md` | operator-facing preflight contract |
| `docs/operations/production-incident-recovery-runbook.md` | severity, recovery and escalation runbook |
| `docs/operations/production-recovery-drill-checklist.md` | drill scenarios and evidence template |
| `docs/operations/production-runtime-policy-traceability-r5.md` | per-policy implementation traceability |
| `docs/operations/production-policy-runtime-alignment-r5.md` | this durable R5 evidence |
| `docs/operations/production-release-risk-register.md` | honest R5 risk-state addendum |
| `apps/api/src/boardtrace_api/app.py` | minimum health and injectable production Redis limiter |
| `apps/api/src/boardtrace_api/core/rate_limit_middleware.py` | production auth/rate/fail-closed middleware |
| `apps/api/src/boardtrace_api/rate_limits.py` | Redis atomic counters and R4 limits |
| `apps/api/src/boardtrace_api/provenance.py` | source allowlist and canonical checksum |
| `apps/api/src/boardtrace_api/api/v1/endpoints/ingestion.py` | provenance fail-closed API boundary |
| `apps/api/src/boardtrace_api/schemas/ingestion.py` | provenance/manual-retry request contract |
| `apps/api/src/boardtrace_api/schemas/health.py` | minimum anonymous health response |
| `apps/api/src/boardtrace_api/services/analysis_cleanup.py` | idempotent terminal submitted-data cleanup |
| `apps/api/src/boardtrace_api/services/analysis_jobs.py` | terminal failure cleanup transaction |
| `apps/api/tests/unit/test_analysis_terminal_failure_service.py` | failure cleanup/audit ordering tests |
| `apps/api/tests/unit/test_production_rate_limits.py` | R4 limit and Redis failure tests |
| `apps/api/tests/unit/test_provenance_policy.py` | allowlist/checksum tests |
| `apps/extension/src/completed-game.ts` | provenance checksum payload |
| `apps/extension/src/popup.ts` | session-only result warning |
| `apps/extension/src/protocol.ts` | provenance fields in extension protocol |
| `apps/extension/tests/protocol.test.ts` | extension provenance contract tests |
| `.dockerignore` | deterministic minimal Docker build context |
| `infrastructure/production-like/Dockerfile.api` | API/worker runtime image with native Stockfish |
| `infrastructure/production-like/Caddyfile` | isolated local reverse-proxy configuration |
| `infrastructure/production-like/compose.yaml` | production-like core service composition |
| `scripts/run_production_like_validation.ps1` | fail-fast build/health/migration/teardown harness |

R5 edits in files that were already unstaged before R5 were intentionally left
unstaged to avoid staging unrelated prior-prompt work. These include
`.env.example`, `package.json`, API configuration/logging/repository/result/
ingestion/worker files, and their overlapping tests. Consequently the working
tree contains the tested R5 behavior, but the index alone is not a complete R5
changeset. All other pre-existing unstaged/untracked web, API, extension and
documentation work was preserved.

## R5-R2 supersession

This R5 report is retained as historical evidence. R5-R2 resolves its two
remaining repository-runtime blockers: the active logging policy is now
metadata-only, and the bounded Redis admission controller plus central
terminal cleanup are integrated with real ingestion/outbox/worker paths.

The clean production-like run is
`bt20dr5r2-20260731T233207-clean`; full evidence and current four-axis status
are in `docs/operations/production-runtime-policy-alignment-r5-r2.md`.
R4-010 and R4-011 are `CLOSED / VERIFIED`; external host, operator, and
provisioning risks remain open.
