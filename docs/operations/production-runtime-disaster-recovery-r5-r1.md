# Prompt 20-D-R5-R1 Runtime Lifecycle and Disaster-Recovery Evidence

## Evidence identity

- RUN_ID: `bt20dr5r1-1785511988-23d1973`
- Timestamp: `2026-07-31T18:33:08+03:00`
- Repository revision: `23d19730e97dd0aa1503202cf3ce04a56f4ff776`
- Decision-package JSON SHA-256:
  `14c05a9cd4a59a8f61796159de7218cb86f628ef1b68ccd2c82fb7e600f763de`
- Validation target: isolated local Docker Linux production-like environment
- Production deployments, external provisioning, real credentials, and external
  BoardTrace system mutations: `0`

## Executive result

The updated `scripts/run_production_like_validation.ps1` completed with exit
code `0`. It preserves the R5 core result and adds current executable evidence
for a real Redis bounded-FIFO admission controller, explicit waiting consent,
waiting cancellation, one 180-second extension, the 180/360-second expiry
boundaries, Redis-unavailable fail-closed behavior, age-encrypted PostgreSQL
backup, local S3-compatible upload, object size/checksum verification, download
checksum verification, and restore into a separate PostgreSQL instance.

This is a substantial R4-011 mitigation result, but it is not full R5-R1
completion. The admission controller is not yet connected to the public
ingestion/outbox lifecycle. Hard analysis timeout, cancellation, queue-expiry,
retry-exhaustion and worker-crash cleanup are not all implemented as one
end-to-end state machine. The separately protected full-PGN sink is prohibited
by the repository's current secure-logging invariant, which says backend logs
must never contain FEN values or request bodies. No raw PGN sink was introduced
without an explicit policy reconciliation.

## Implemented production-like validation

| Area | Executed assertion | Result |
| --- | --- | --- |
| Core | PostgreSQL, Redis, Alembic head, API, worker and Caddy health | PASS |
| Worker queue | Celery outbox probe is observed as succeeded by the worker | PASS |
| Admission | first two jobs active; one active job per user; later admission requires explicit consent | PASS |
| Bounded FIFO | three waiting jobs receive FIFO positions; fourth is rejected | PASS |
| Cancellation | a waiting job is removed and capacity is reusable | PASS |
| Wait policy | 180-second initial expiry, one explicit extension, and 360-second maximum | PASS |
| Redis failure | authenticated request returns 503, `Retry-After: 60`, and `rate_limit_state_unavailable`; Redis then recovers healthy | PASS |
| Backup | PostgreSQL 16 custom-format logical backup encrypted with an ephemeral age identity | PASS |
| S3 substitute | encrypted object uploaded to pinned local MinIO | PASS |
| Object integrity | existence, exact content length, SHA-256 metadata and downloaded SHA-256 | PASS |
| Restore | object decrypted and restored with PostgreSQL 16 tools into a separate database; Alembic version row verified | PASS |
| Cleanup | plaintext working files and private age identity removed; all test containers, networks and volumes removed | PASS |

The backup workflow uploads only `boardtrace.dump.age`. Its local test identity
is generated per run and deleted after successful restore. This validates the
mechanics, not production R2 credentials, 30-day object retention, daily
scheduling, or key custody.

## Queue coverage boundary

`apps/api/src/boardtrace_api/queue_admission.py` uses atomic Redis Lua scripts
for admission, cancellation, extension, expiry and FIFO promotion.
`scripts/validate_queue_lifecycle.py` executes those scripts against the same
Redis service used by the production-like API and worker.

The module is currently an integration component, not the authoritative API
workflow. Completed-game ingestion still creates a PostgreSQL job/outbox event
without consulting it, and no owner-scoped consent/cancel/extension endpoint
has been added. Therefore the Docker assertions prove the controller semantics,
not deployment-ready end-to-end enforcement.

## Timeout, late result and terminal cleanup assessment

- Celery production settings retain a 170-second soft limit and 180-second hard
  limit, with automatic application retry disabled.
- Stockfish timeout and process cleanup, cancellation re-raise, terminal failure
  cleanup ordering, and Redis rate-limit behavior passed 38 focused unit tests.
- Existing generation/lease ownership checks reject stale completion and stale
  persistence attempts, but the current R5-R1 Docker harness does not create a
  real 180-second worker race and prove its resulting database cleanup.
- Success and accepted terminal failure delete submitted game/provenance data in
  their transaction. Queue expiry, API cancellation, hard timeout,
  retry-exhaustion and worker-loss paths do not all invoke that cleanup today.

Accordingly, `analysis timeout`, `late-result rejection`, and `cleanup across
every terminal path` remain `PARTIAL / BLOCKED`, not PASS.

## Repeatable commands and observed results

| Command | Exit | Result |
| --- | ---: | --- |
| `.venv\\Scripts\\ruff.exe format --check ...` | 0 | 3 R5-R1 Python files formatted |
| `.venv\\Scripts\\ruff.exe check ...` | 0 | focused lint PASS |
| `.venv\\Scripts\\mypy.exe ...` | 0 | focused type check PASS |
| `.venv\\Scripts\\pytest.exe -q apps/api/tests/unit/test_stockfish_engine.py apps/api/tests/unit/test_analysis_terminal_failure_service.py apps/api/tests/unit/test_production_rate_limits.py` | 0 | 38 passed; cache permission warning only |
| `.\\scripts\\run_production_like_validation.ps1` | 0 | final full harness PASS in 102.0 seconds |
| post-run filtered Docker container/volume/network queries | 0 | all returned empty |

The successful harness observed Docker Engine `29.6.1` on Linux, Alembic
`f03a4b5c6d7e (head)`, Redis `PONG`, `queue lifecycle validation passed`,
`Redis-unavailable fail-closed validation passed`, and `encrypted backup upload
and isolated restore validation passed`. The encrypted object was approximately
52.7 KiB for this isolated fixture database.

During development, three failures were retained as engineering findings and
fixed before the final run: PostgreSQL 15 client/server-16 mismatch, stale
backup-image reuse until an explicit Compose build was added, and restore-role
ownership mismatch until `pg_restore --no-owner` was used.

The Docker builds contacted Docker Hub, Debian package mirrors and PyPI for
declared build inputs. They contacted no production BoardTrace target. All
service credentials in the composition are explicit test-only values.

## Four separate status axes

| Axis | Status |
| --- | --- |
| Decision completeness | PASS — 28/28 authoritative decision fields remain resolved |
| External provisioning completeness | BLOCKED — no production resources or real secrets were provisioned |
| Deployment executability | BLOCKED — queue/API integration, complete terminal cleanup and PGN-policy reconciliation remain |
| Launch authorization | NOT GRANTED — this run neither requests nor grants deployment or launch |

## Required follow-up

1. Integrate admission with server-owned ingestion/outbox state and add
   authenticated consent, cancel and one-time extension operations.
2. Implement one terminalization service used by queue expiry, user
   cancellation, soft/hard timeout recovery, retry exhaustion and worker-loss
   recovery; prove stale/late result rejection and cleanup in PostgreSQL/Redis.
3. Resolve the direct conflict between the approved 24-hour full-PGN technical
   log and the repository rule forbidding FEN/request-body logging before any
   PGN sink is implemented.
4. Repeat this harness after those changes, then perform separately authorized
   host provisioning, backup scheduling/key custody and a staffed recovery drill.

## R5-R2 completion addendum

R5-R2 completed items 1-3 above. It explicitly superseded the former full-PGN
policy, integrated Redis admission with the production-like API/outbox/worker
lifecycle, and converged cancellation, expiry, timeout, worker loss, duplicate
callbacks, late results, cleanup, and capacity release on authoritative paths.

Run `bt20dr5r2-20260731T233207-clean` passed the full harness without audit
warnings and verified complete resource teardown. R4-010 and R4-011 are now
`CLOSED / VERIFIED`. Item 4 remains external work and is not authorized by this
record. See `docs/operations/production-runtime-policy-alignment-r5-r2.md`.
