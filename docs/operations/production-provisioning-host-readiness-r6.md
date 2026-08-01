# BoardTrace R6 Provisioning and Host-Readiness Evidence

## 1. Mode and authorization

- Mode: `MODE A — PLAN_AND_DRY_RUN`
- Basis: Prompt 20-D-R6 defaults to Mode A; no explicit Mode B authorization
  or secure real credentials were supplied.
- Recorded at: `2026-08-01T02:16:22+03:00`
- R5-R2 source run: `bt20dr5r2-20260731T233207-clean`
- R6 corrected-harness run: `bt20dr6-20260801T025200-fixed2`
- Production deployment/public traffic: `NO / NO`
- External mutation count: `0`

## 2. R5-R2 evidence qualification

All 15 previously incomplete executions are required because they cover
transaction durability/concurrency or production configuration failure modes.
None remains skipped, xfailed, or blocked.

| Test identity/group                                                           | Requirement                           | Prior reason               | R6 rerun | Equivalent evidence                                                | Closure impact         |
| ----------------------------------------------------------------------------- | ------------------------------------- | -------------------------- | -------- | ------------------------------------------------------------------ | ---------------------- |
| `test_failing_before_commit_hook_rolls_back_ingestion_durably`                | failed transaction leaves no game/job | PostgreSQL URL absent      | PASS     | direct PostgreSQL assertion; no substitute relied upon             | R4-010 retained        |
| `test_no_op_before_commit_hook_durably_commits_ingestion`                     | successful transaction durability     | PostgreSQL URL absent      | PASS     | direct PostgreSQL assertion                                        | R4-010 retained        |
| `test_ingestion_endpoint_resolves_overridden_terminal_observer`               | observer wiring on real DB path       | PostgreSQL URL absent      | PASS     | direct endpoint/DB assertion                                       | R4-010 retained        |
| `test_concurrent_identical_ingestion_returns_one_authoritative_game_and_job`  | idempotent concurrent ingestion       | PostgreSQL URL absent      | PASS     | direct concurrent PostgreSQL assertion                             | R4-010/R4-011 retained |
| `test_concurrent_conflicting_ingestion_rejects_loser_without_duplicate_state` | conflicting concurrent ingestion      | PostgreSQL URL absent      | PASS     | direct concurrent PostgreSQL assertion                             | R4-010/R4-011 retained |
| `test_unexpected_error_hides_internal_details_in_production`                  | safe production error disclosure      | Windows pytest temp denied | PASS     | direct rerun; prior logging tests were similar but not substituted | R4-010 retained        |
| `test_production_wildcard_cors_is_rejected`                                   | production CORS fail-closed           | Windows pytest temp denied | PASS     | direct rerun                                                       | R4-010 retained        |
| `test_production_explicit_configuration_is_accepted`                          | complete production settings          | Windows pytest temp denied | PASS     | direct rerun                                                       | R4-010 retained        |
| four `test_production_missing_critical_configuration_fails_fast[...]` cases   | DB/JWT/Redis/pepper absence fails     | Windows pytest temp denied | 4 PASS   | direct rerun                                                       | R4-010 retained        |
| `test_production_rejects_development_network_defaults`                        | no development networking             | Windows pytest temp denied | PASS     | direct rerun                                                       | R4-010 retained        |
| `test_production_rejects_invalid_stockfish_path`                              | engine path fail-fast                 | Windows pytest temp denied | PASS     | direct rerun                                                       | R4-010 retained        |

Rerun command: `scripts/run_r6_evidence_qualification.ps1`. It uses an ignored
repository-local temp directory, loopback-only PostgreSQL 16, migrates through
Alembic head `g14b5c6d7e8f`, runs 10 filesystem-dependent and 5 PostgreSQL
tests, then removes its container, volume and network. Result: `15/15 PASS`.

The qualification found and removed one stale R4 contract field:
`BOARDTRACE_PGN_LOG_RETENTION_HOURS`. It is now explicitly rejected; production
requires `BOARDTRACE_DIAGNOSTIC_LOG_POLICY=metadata-only` and
`BOARDTRACE_RAW_GAME_LOGGING=prohibited`. R4-010 and R4-011 remain
`CLOSED / VERIFIED` after correction and rerun.

The first R6 stability probe also exposed a genuine audit-path defect: an
otherwise valid random UUID containing a bounded UCI-looking segment such as
`b7a6` could be rejected as game content and turn successful ingestion into a
500 response. The diagnostic validator/filter is now field-aware for bounded
server identifiers, while request/message/game-content checks remain strict.
All production runtime audit calls use the non-propagating adapter, so a log
validation or sink failure cannot alter lifecycle state. Focused regression
tests pass, the corrected full Docker harness passes, and five additional
back-to-back integrated lifecycle iterations pass. No failed run was hidden.

## 3. Provisioning manifest

Machine source:
`infrastructure/production/provisioning-manifest.r6.json`.

Approved static values are Hetzner Cloud, project `BoardTrace Pilot`, one CX33
named `boardtrace-pilot-01` in `nbg1`, Ubuntu 24.04 x86_64, public TCP
80/443/48227 only, hostname `boardtrace.duckdns.org`, private Docker services,
R2 bucket `boardtrace-pilot-backups` with 30-day ciphertext retention, and GHCR
repository `ghcr.io/mustafabedirr/boardtrace` using an immutable version/digest.

Generated server/network/provider IDs are null. Required secrets are recorded
by name and `NOT_PROVIDED`, never by value. Pending operational inputs include
two SSH-key fingerprints, deletion-protection/IPv6 choices, image version and
digest, age public recipient, real environment values and drill approval.

## 4. External mutation plan

The exact 12-step plan is
`infrastructure/production/external-mutation-plan.r6.json`. Each entry includes
system, action, resource, purpose, expected result, rollback, cost category,
reversibility, downtime, credential names and verification command. Current
prices are intentionally not asserted and must be confirmed from the provider
before an authorized Mode B execution. Executed actions: none.

## 5. Hetzner plan

Account/project/server status: `NOT PROVISIONED`.

Mode B instructions, not executed:

1. select/create only project `BoardTrace Pilot` and record the current quote;
2. attach only the approved primary public key (fingerprint evidence only);
3. create exactly one `CX33`, `nbg1`, `ubuntu-24.04`, IPv4 required, optional
   IPv6 pending decision, with labels from the manifest;
4. apply a firewall allowing inbound TCP 80/443/48227 only; do not deploy;
5. decide and record deletion protection before relying on it;
6. verify `hcloud server list` shows no accidental second server;
7. rebuild by recreating Ubuntu 24.04 from the version-controlled bootstrap,
   then restoring only approved encrypted data.

## 6. Host hardening and base readiness

Repository artifacts validate, but no real host was changed. The bootstrap is
now two-stage: key-only ports 22/48227 remain until a second established key
session on 48227 creates a root-owned `0600` marker; only the finalizer removes
port 22. Rollback restores the key-only two-port policy and UFW access.

Mode B must verify Ubuntu 24.04, UTC and clock sync, supported Docker/Compose,
daemon not bound to TCP, JSON log rotation, restrictive `/opt/boardtrace`
ownership, root-only `.env`, disk/memory/swap choice, updates, firewall,
listeners and Fail2ban. R4-001 is `READY_FOR_HOST_VERIFICATION / BLOCKED`.

## 7. DuckDNS and TLS

- DNS record: not created/changed/verified.
- Secret-safe updater command target:
  `curl --silent --show-error --fail --config /root/boardtrace/duckdns.curl.conf`.
- Validation: query authoritative/default resolution plus independent resolvers
  and verify only the approved VPS address and observed TTL.
- Renewal health: root-owned updater timer must alert after consecutive failure.
- Permanent-domain migration: change contract/configured endpoints, reissue
  TLS, update extension/CORS/trusted hosts, validate, then retire DuckDNS.

`Caddyfile.r6` is maintenance-only: admin API off, automatic HTTPS/redirect for
the one hostname, no reverse proxy and no Dozzle/Kuma route. DNS/certificate/
external handshake remain pending Mode B; public API traffic remains disabled.

## 8. Cloudflare R2

Bucket and credentials do not exist or were not inspected. The lifecycle
specification expires objects after 30 days. A future credential must be
bucket-scoped to necessary list/read/write and test cleanup only, never
account-admin. The VPS receives only the age public recipient; the private key
remains off-host. A Mode B probe must use synthetic data, upload ciphertext,
verify size/SHA-256, restore to an isolated DB, delete permitted test objects
and leave no plaintext dump.

## 9. GHCR

Repository reference validates. An immutable approved version and digest are
still pending; `latest` is prohibited. Future credential scope is
`packages:read` only. Mode B may authenticate/pull/inspect the approved image
without starting application containers and must record only digest and
architecture, then support `docker logout` and image removal rollback.

## 10. Telegram

Bot `BoardTrace Alerts` and group `BoardTrace Pilot` are planned, not created or
inspected. Mode B must grant minimum permissions and send one explicitly
labelled provisioning test containing no sensitive/game data. Token and chat
identifier belong only in the root-only secret mechanism and never evidence.

## 11. Production environment and no-bypass preflight

The R5-R2 environment contract is code-derived and now metadata-only. Real
`.env` assembly is prohibited in Mode A. Repository gates pass independently;
the complete production preflight remains `BLOCKED AS DESIGNED` at absent real
values. There is no force/skip option. R4-009 is
`IMPLEMENTED_PENDING_REAL_VALUES / BLOCKED`.

## 12. Secondary operator and first recovery drill

No Ahmet account/key/sudo rule was installed on a host and no staffed drill was
performed. Static dispatcher/sudoers/onboarding/revocation artifacts validate.
The first real drill must cover application stop, worker failure, Redis loss,
previous-known-good rollback, disk restricted mode, health and communication
handoff with synthetic/empty data and public traffic disabled. R4-007 is
`READY_FOR_PROVISIONING / BLOCKED`.

## 13. Production preflight and go/no-go

See `production-preflight-evidence-r6.md` and
`production-technical-go-no-go-packet-r6.md`. Provider/host/operator categories
remain pending. Technical go/no-go is not passed and no launch date was
calculated.

## 14. Risk status

| Risk   | R6 state                                  | Reason                                                                |
| ------ | ----------------------------------------- | --------------------------------------------------------------------- |
| R4-001 | READY_FOR_HOST_VERIFICATION / BLOCKED     | repository two-session controls pass; real host absent                |
| R4-007 | READY_FOR_PROVISIONING / BLOCKED          | templates pass; account, deny tests and drill absent                  |
| R4-009 | IMPLEMENTED_PENDING_REAL_VALUES / BLOCKED | no-bypass code exists; real values/preflight absent                   |
| R4-010 | CLOSED / VERIFIED                         | all 15 incomplete R5-R2 tests now pass; stale PGN env field corrected |
| R4-011 | CLOSED / VERIFIED                         | corrected full Docker harness and 5x lifecycle stability loop pass    |

## 15. Status axes

| Axis                               | Status                                |
| ---------------------------------- | ------------------------------------- |
| R6 mode                            | PLAN_AND_DRY_RUN                      |
| Decision package completeness      | PASS — 28/28, invalid 0, conflict 0   |
| R5-R2 evidence qualification       | PASS — 15/15 rerun                    |
| Runtime-policy alignment           | PASS                                  |
| External provisioning completeness | BLOCKED                               |
| Host hardening                     | READY_FOR_HOST_VERIFICATION / BLOCKED |
| Secondary-operator readiness       | READY_FOR_PROVISIONING / BLOCKED      |
| Production preflight               | BLOCKED — real values absent          |
| Deployment executability           | BLOCKED                               |
| Technical go/no-go                 | NOT YET PASSED                        |
| Closed-pilot authorization         | NOT YET GRANTED                       |
| Public-launch authorization        | NOT GRANTED                           |
| Prompt 20-D release                | BLOCKED                               |

## 16. Mutation ledger and production state

The ledger records zero created, modified, deleted or remaining R6 external
resources and zero unexpected mutations. No application was deployed, no
public traffic enabled, no pilot users created, no external credential created,
and no production system contacted or mutated.

## 17. Honest limitations

Mode A cannot verify account ownership, provider prices, server identity,
effective host policy, DNS/TLS, real bucket lifecycle, registry visibility,
Telegram delivery, root-only secret permissions, operator access or drill
performance. Those claims remain blocked until an explicitly authorized,
bounded Mode B run with secure credentials and per-step evidence. A successful
Mode B would still prepare—not grant—technical go/no-go or launch.

## 18. Validation summary

| Validation                                   | Exit/result                                                                    |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| `scripts/run_r6_evidence_qualification.ps1`  | `0`; 10 temp-path + 5 PostgreSQL tests PASS                                    |
| Python Ruff format/lint + strict Mypy        | `0`; 187 files clean                                                           |
| R6/control/logging/request-ID focused pytest | `0`; 79 PASS                                                                   |
| decision completeness gate                   | `0`; 28/28, invalid 0, conflicts 0                                             |
| host-hardening + manifest validators         | `0`; PASS, external mutations 0                                                |
| both Docker Compose config gates             | `0`; PASS                                                                      |
| full production-like harness                 | `0`; RUN_ID `bt20dr6-20260801T025200-fixed2`, PASS and teardown                |
| integrated lifecycle stability loop          | `0`; five consecutive PASS                                                     |
| TypeScript typecheck                         | `0`; PASS                                                                      |
| Vitest                                       | `0`; 20 files / 153 tests PASS                                                 |
| focused R6 Prettier                          | `0`; PASS (PowerShell/Caddy use native validators)                             |
| full repository ESLint                       | `1`; 22 errors in pre-existing/unrelated web files; no R6 JS/TS artifact added |
| no-value production preflight                | expected `1`; fails closed at real environment values, no bypass               |

The full ESLint failure is not reclassified as an R6 pass and was not fixed
outside this prompt's scope. The production preflight failure is the required
Mode A outcome, lists names/policy mismatches only, and exposes no values.
