# BoardTrace R5-R2 Runtime and Policy Alignment Evidence

## Evidence identity

- Scope: Prompt 20-D-R5-R2
- Authority: Mustafa Bedir
- Intake source SHA-256:
  `e58bb559ab3eabeb650a8ac01f1fb6b368ae5ecbced02ebcfde986b98566df91`
- Repository base revision: `23d19730e97dd0aa1503202cf3ce04a56f4ff776`
- Clean production-like run ID: `bt20dr5r2-20260731T233207-clean`
- Recorded at: `2026-07-31T23:32:07+03:00`
- Production mutations: `0`

This record supersedes the blocked R5/R5-R1 conclusions for R4-005, R4-010,
and R4-011. It preserves those documents as historical evidence. R4-001,
R4-007, and R4-009 remain open and deployment-blocking.

## Authoritative policy result

The former 24-hour full-PGN technical-log policy is `SUPERSEDED`. The active
policy is metadata-only diagnostics. Full PGN, FEN, raw move lists, game
request bodies, reconstructable engine input/output, credentials, email
addresses, and full IP addresses are prohibited from every log category.

The runtime enforces a typed metadata allowlist and central unsafe-content
suppression. Unsafe records are replaced with the safe
`diagnostic_content_suppressed` event; logging failure cannot break the core
transaction. Dozzle binds only to host loopback for an SSH tunnel and is not a
raw game-content store.

## Integrated lifecycle result

| Control | Result | Evidence |
| --- | --- | --- |
| maximum active analyses `2` | PASS | Redis atomic admission and integrated HTTP flow |
| per-user active/waiting limit `1` | PASS | shared Redis user/job mapping |
| explicit consent before waiting | PASS | consent-required response and owner consent endpoint |
| bounded FIFO waiting queue `3` | PASS | queue positions, full-queue `429`, FIFO promotion |
| initial wait `3` minutes | PASS | Redis deadline contract |
| one additional `3`-minute extension | PASS | one-use extension state |
| maximum queue lifetime `6` minutes | PASS | expiry sweep after extended deadline |
| outbox only after active admission | PASS | PostgreSQL outbox assertions |
| cancellation | PASS | owner cancellation through central terminal service |
| analysis timeout | PASS | hard-failure terminal path and deterministic integration callback |
| worker loss / retry exhaustion | PASS | no automatic retry; terminal worker-loss path |
| late and duplicate callback rejection | PASS | first terminal write wins; late completion rejected |
| cleanup on terminal paths | PASS | game source, moves, and ingestion hash deleted |
| capacity release and FIFO promotion | PASS | terminal release creates promoted job outbox |
| Redis unavailable | PASS | fail closed with HTTP `503` and `Retry-After: 60` |
| live-game protection | PASS | existing worker guard remains before engine invocation |

The timeout and worker-loss integration checks invoke the same worker terminal
helpers used by Celery signals; the harness does not wait three real minutes or
kill an operating-system worker process. The real time limits remain configured
at 170-second soft and 180-second hard limits, with no automatic retry.

## Disaster-recovery and composition result

The repeatable entry point was
`scripts/run_production_like_validation.ps1`. The clean run returned exit code
zero and verified:

- Docker Engine 29.6.1 on Linux;
- PostgreSQL readiness and Alembic head `g14b5c6d7e8f`;
- Redis readiness and isolated FIFO lifecycle;
- integrated admission and terminal cleanup;
- Redis-unavailable fail-closed behavior;
- API, Caddy, PostgreSQL, Redis, worker, MinIO, and isolated restore health;
- logical PostgreSQL backup encrypted with `age` before upload;
- S3-compatible MinIO object existence and size (`53.1 KiB`);
- encrypted-object download and SHA-256 integrity verification;
- restore into isolated PostgreSQL and validation of restored data;
- removal of all `boardtrace-r5` containers, volumes, and network after the run.

No raw PGN/FEN warning or analysis-audit failure appeared in the clean run.

## Automated quality evidence

- Ruff: PASS.
- Mypy: PASS for API and lifecycle validation sources.
- Focused safe-logging/audit tests: `18 passed`.
- Production-decision plus safe-logging/audit tests: `32 passed`.
- Additional lifecycle/configuration selection: `20 passed`, `5 skipped`
  because no local PostgreSQL test URL was supplied; 10 setup errors were the
  known Windows sandbox denial for pytest's user-temp directory, not assertion
  failures.

## Risk and release effect

- R4-005: `CLOSED / SUPERSEDED`.
- R4-010: `CLOSED / VERIFIED` for repository runtime-policy alignment.
- R4-011: `CLOSED / VERIFIED` for current production-like integration evidence.
- R4-001, R4-007, R4-009: `MITIGATE / OPEN`, deployment blockers.
- Decision completeness: expected `PASS`.
- External provisioning completeness: remains `BLOCKED`.
- Deployment executability: remains `BLOCKED`.
- Closed-pilot launch authorization: `NOT_YET_GRANTED`.
- Public launch authorization: `NOT_GRANTED`.

This evidence does not provision an external service, deploy production, open
public traffic, create credentials, complete host/operator controls, or grant
launch authorization.
