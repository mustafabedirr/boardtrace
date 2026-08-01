# Production Runtime Policy Traceability — R5

The R4 package remains the policy authority. `PASS` below means the listed
repository behavior has current local evidence; it does not prove a production
host or provisioned external service.

| R4 policy                        | Implementation                                                                | Verification                                                                | Status / remaining work                                                                                                         |
| -------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| D20R2-014 key-only SSH on 48227  | `infrastructure/production/ssh/`                                              | `scripts/validate_host_hardening.py`; `tests/python/test_host_hardening.py` | Repository PASS; production effective `sshd -T`, firewall and Fail2ban BLOCKED                                                  |
| D20R2-015 secondary recovery     | recovery dispatcher, scoped sudoers, incident runbook                         | `tests/python/test_secondary_operator_readiness.py`                         | READY_FOR_PROVISIONING; real account/key/permission check and first drill BLOCKED                                               |
| D20R2-016 external inputs        | production environment contract and preflight                                 | `tests/python/test_production_environment.py`                               | Repository PASS; preflight with real values BLOCKED                                                                             |
| D20R2-017 session-only results   | one successful owner delivery consumes the generation; extension warning      | API result repository/service; extension protocol tests                     | PARTIAL: browser-session termination cannot invalidate an undelivered server result                                             |
| D20R2-018 delete on terminal     | `services/analysis_cleanup.py`; success/failure transaction hooks             | terminal failure unit tests                                                 | PARTIAL: timeout, cancellation, queue-expiry and worker-crash sweeper paths are absent                                          |
| D20R2-019 queue consent/FIFO     | existing PostgreSQL outbox and Celery queue                                   | no R5 compliant queue suite                                                 | BLOCKED: consent, bounded Redis FIFO, cancel and 3+3 minute extension are absent                                                |
| D20R2-020 timeout/retry          | worker hard limit 180 seconds; automatic retry disabled; manual retry limiter | settings, worker and rate-limit tests                                       | PARTIAL: late-result race and terminal timeout cleanup are not fully proven                                                     |
| D20R2-012 rate limiting          | production Redis middleware and atomic Lua counter                            | `test_production_rate_limits.py`                                            | PARTIAL: basic limits/fail-closed pass; concurrent increment, retry-window expiry and retained violation-log store are unproved |
| D20R2-021 provenance             | version-controlled Lichess/extension allowlist and canonical SHA-256          | provenance and extension protocol tests                                     | PARTIAL: manual PGN is rejected by allowlist, but provenance deletion depends on incomplete terminal coverage                   |
| D20R2-022 full-PGN technical log | no R5 PGN sink was added                                                      | repository logging prohibition remains                                      | BLOCKED: isolated sink and enforced 24-hour deletion are absent; raw PGN is not placed in ordinary logs                         |
| D20R2-023 live-game guard        | server-owned completed-game validation immediately before analysis            | existing engine/security tests                                              | PARTIAL: queued external-source revalidation and retry-during-live tests remain absent                                          |
| D20R2-024 minimum health         | anonymous root `/health` returns status only                                  | `apps/api/tests/test_health.py`                                             | PASS locally; production routing unverified                                                                                     |

Because several D20R2 runtime rows are partial or blocked, R4-010 remains a
deployment blocker. None of the partial rows may be treated as an operational
waiver.

## R4-011 current Docker evidence addendum

The Docker Linux daemon became available after the initial R5 run. The
production-like composition in `infrastructure/production-like/compose.yaml`
currently verifies image build, PostgreSQL readiness, transactional Alembic
migration to head, Redis readiness, API minimum health through Caddy,
authenticated API-to-PostgreSQL readiness through Redis-backed middleware, a
Redis/Celery outbox probe completed by the worker, isolated networking, and
complete container/network/volume teardown. This core composition validation
is `PASS`.

R4-011 remains `PARTIAL / BLOCKED`, rather than closed, because the current
composition does not yet exercise the full required queue/timeout/cancellation/
cleanup/Redis-failure suite or encrypted backup/upload/restore workflow.

## R5-R1 addendum

Evidence RUN_ID `bt20dr5r1-1785511988-23d1973` supersedes the Docker statements
above. The current harness now passes the real Redis admission-controller
contract (consent, two active, three FIFO waiters, per-user exclusion,
cancellation, one 180-second extension and 360-second maximum), Redis
fail-closed/recovery, and age-encrypted backup/MinIO object integrity/isolated
PostgreSQL restore. See
`docs/operations/production-runtime-disaster-recovery-r5-r1.md`.

R4-011 remains `PARTIAL / BLOCKED`: the admission controller is not connected
to ingestion/outbox state, and end-to-end hard-timeout/cancellation/queue-expiry/
worker-loss cleanup is absent. R4-010 remains `PARTIAL / BLOCKED` for the same
runtime-integration gap and the unresolved full-PGN logging policy conflict.

## R5-R2 supersession and integration result

The conclusions immediately above are historical. R5-R2 replaces the
full-PGN requirement with authoritative metadata-only logging and connects the
Redis admission controller to authenticated ingestion, consent, outbox
creation, worker terminalization, cancellation, expiry, timeout, worker-loss,
late-result rejection, cleanup, capacity release, and FIFO promotion.

Clean run `bt20dr5r2-20260731T233207-clean` passed the integrated lifecycle,
Redis fail-closed, encrypted backup/object verification/isolated restore, and
complete teardown. R4-010 and R4-011 are therefore `CLOSED / VERIFIED` for
repository/runtime scope. R4-001, R4-007, and R4-009 remain open blockers. See
`docs/operations/production-runtime-policy-alignment-r5-r2.md`.

## R6 evidence qualification

R6 Mode A directly reran the 10 Windows-temp setup failures and five skipped
PostgreSQL transaction/concurrency tests; all 15 passed. It also removed the
stale R4-era PGN-log-retention environment key and made metadata-only/no-raw-
game logging mandatory in production preflight. R4-010 and R4-011 remain
`CLOSED / VERIFIED`. The corrected R6 harness run
`bt20dr6-20260801T025200-fixed2` also proves that server UUIDs with move-like
segments no longer fail ingestion, while logging failures remain isolated;
five consecutive lifecycle iterations pass. External host/operator/
provisioning controls remain blocked with zero mutations. See
`docs/operations/production-provisioning-host-readiness-r6.md`.
