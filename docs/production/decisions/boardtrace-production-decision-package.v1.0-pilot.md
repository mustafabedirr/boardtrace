# BoardTrace Production Decision Package

## Revision identity

- Document version: `v1.0-pilot`
- Decision-intake revision: `R4`
- Prior repository revision: `v1.0-pilot/R3`
- Original package date: 29 July 2026
- R4 recording timestamp: `2026-07-31T16:40:14+03:00`
- Accountable decision owner: Mustafa Bedir
- R4 authority: Prompt 20-D-R4 authoritative intake
- R4 source SHA-256: `2ecc10d488c62a4acfac4652384f1053be7ae2ef8ecd2ebbeb8e157feb03f1dd`
- Scope: closed production pilot, five invited users
- Binding invariant: `NO ENGINE OUTPUT DURING LIVE GAMES`

R4 preserves the decisions previously integrated by R3 and closes the human
decision gaps D20R2-012 and D20R2-014 through D20R2-028. It does not provision
infrastructure, implement runtime policy, complete technical go/no-go, deploy
production, or authorize launch.

## Preserved R3 decisions

D20R2-001 through D20R2-011 and D20R2-013 retain the v1.0-pilot values:
Hetzner Cloud `nbg1` CX33 target; Ubuntu 24.04 and Docker on one VPS;
self-managed PostgreSQL and Redis; DuckDNS/Caddy/Let's Encrypt; Uptime Kuma;
Telegram alerts; root-only production `.env`; private GHCR and GitHub Actions;
five-user workload forecast; bounded concurrency/queue sizing; and monitoring
thresholds. D20R2-001, 003-007, and 009 remain `PENDING_PROVISIONING`.

## R4 decisions

### D20R2-012 — Production rate limits

Status: `DECIDED`. Owner: Mustafa Bedir.

- Authenticated user: 30 requests/minute; global authenticated traffic:
  120 requests/minute.
- Analysis start: 3/user/10 minutes. Same-game manual retry:
  2/15 minutes in addition to the start limit. Automatic retry is disabled.
- Existing limits remain: 1 active analysis/user, 2 globally, queue size 3.
- Anonymous application API access is prohibited. Only minimum-information
  `/health` is anonymous, at 30 requests/minute/IP, without version,
  infrastructure, database, dependency, secret, or configuration metadata.
- Failed login: 10/IP/15 minutes, followed by a 30-minute block.
- Violations return 429 with accurate `Retry-After`.
- All counters use shared Redis state. Redis failure is fail-closed for
  analysis-start and sensitive/state-changing endpoints; only `/health`
  remains available. The response is 503 with `Retry-After: 60`.
- Violation logs contain masked user/IP, endpoint, category, and timestamp;
  retention is seven days with automatic rotation.

### D20R2-014 — On-call and incident roles

Status: `DECIDED`. Mustafa Bedir is primary on-call, incident commander, and
primary communications lead. Ahmet Bedir is secondary on-call and fallback
communications lead only when Mustafa cannot be reached.

Ahmet may stop service, restart containers, roll back to the previous
known-good image, and perform documented basic recovery. He may not make
permanent architecture or policy changes, deploy a new release, approve risk
acceptance/public launch/pilot expansion, or exercise authority outside the
runbook. This is a role decision, not proof of provisioned access.

Response-start targets are SEV-1 15 minutes, SEV-2 one hour, SEV-3 24 hours.
SEV-1 fails closed and protects the live-game invariant. Incident records are
retained one year for SEV-1/2 and 90 days for SEV-3. Post-incident review is
mandatory for SEV-1/2 and optional for SEV-3, with summary, impact, timeline,
root cause, actions, corrective actions, owner, and target date.

### D20R2-015 — PITR and recovery

Status: `DECIDED`. PITR is explicitly disabled for the closed five-user pilot.
The model is one encrypted full logical PostgreSQL backup daily, 30-day R2
retention, monthly restore testing, approximately 24-hour RPO, and four-hour
RTO. Reassess after the pilot or material user/data/criticality/managed
PostgreSQL/WAL changes. The no-PITR exposure is accepted in R4-006.

### D20R2-016 — Privacy

Status: `DECIDED`. Data minimization applies. Persist only internal user ID,
username/email, authentication records, and technical security logs. Exclude
behavioral profiling, unnecessary analytics, marketing data, and permanent
game/analysis history by default. Active account data remains while the account
is active; verified deletion requests complete within 30 days, with backup
copies aging out through the normal 30-day rotation. Authentication/security
logs rotate after seven days. Sharing is prohibited except legal necessity.

The pilot Telegram group may initiate access/deletion requests, but sensitive
details move to a private channel. Processing starts only after a link/code sent
to the registered email verifies identity. Access responses are due within 30
days. A short notice and full-policy link must be visible before processing.

### D20R2-017 — Data provenance

Status: `DECIDED`. Temporarily record source platform, source game ID,
acquisition method, and checksum for each analysis; delete them at success or
failure. Source mismatch, unsupported/unverifiable sources, and default manual
PGN fail closed before analysis. The supported-source allowlist is
version-controlled, code-reviewed, tested, and CI-gated; it is not mutable by
environment or admin UI. Provenance-error logs rotate after seven days.

This authoritative R4 meaning supersedes R3's incomplete artifact-provenance
interpretation for D20R2-017.

### D20R2-018 — User and incident communications

Status: `DECIDED`. The BoardTrace Pilot Telegram group is the primary channel.
Initial notices: SEV-1 within 30 minutes, SEV-2 within two hours. Updates:
SEV-1 every hour, SEV-2 every four hours. SEV-3 is communicated only when it
affects users. Closure messages contain impact, start/end, current status, and
required user action. Planned maintenance receives 24 hours' notice for the
Sunday 02:00-04:00 Türkiye/UTC+3 window. Emergency work may start without
advance notice for security/data-integrity risk. Security disclosures omit
attack details and sensitive infrastructure information.

### D20R2-019 — Closed-pilot launch window

Status: `DECIDED`. The real conditional window is the first Sunday
02:00-04:00 Türkiye/UTC+3 after every mandatory technical go/no-go check passes.
Mustafa Bedir is launch authority. This decision grants neither launch nor
deployment approval. Closed-pilot authorization is `NOT YET GRANTED`; public
launch is `NOT GRANTED`.

## D20R2-020 through D20R2-027 — Role-scoped sign-offs

All were recorded from the R4 authoritative intake at
`2026-07-31T16:40:14+03:00` and are separately `APPROVED` by Mustafa Bedir:

| ID | Role | Scope |
| --- | --- | --- |
| D20R2-020 | Production Product Owner | pilot scope, five-user limit, behavior, success criteria, no public launch |
| D20R2-021 | Production Technical Owner | architecture, composition, data services, deployment/rollback, go/no-go, compatibility |
| D20R2-022 | Production Security Owner | access, firewall, secrets/logs, backup encryption, fail-closed invariant |
| D20R2-023 | Production Privacy Owner | minimization, retention/deletion, requests, notice, sharing |
| D20R2-024 | Production Operations Owner | VPS/OS/Docker, monitoring, recovery, deployment/rollback, incidents |
| D20R2-025 | Reliability / Availability Owner | RTO/RPO, recovery, capacity, queue/timeout, monitoring, single-VPS risk |
| D20R2-026 | Data / Provenance Owner | verification, metadata/checksum, allowlist, mismatch, error retention |
| D20R2-027 | Launch / Release Approver | technical go/no-go evaluation, pilot deployment/launch, expansion, rollback |

Mustafa holds all eight roles. There is no independent organizational reviewer.
Every sign-off links to R4-003. D20R2-027 does not assert a passed technical
go/no-go, executable deployment, closed-pilot authorization, or public launch.

## D20R2-028 — Risk register

All records are owned by Mustafa Bedir and recorded on the R4 timestamp.
`ACCEPT` requires a review/expiry; expired acceptance fails closed. `MITIGATE`
remains a deployment blocker until implementation and verification evidence
exists and cannot be manually bypassed.

| Risk | Title | Disposition | State | Review/expiry | Deployment blocker |
| --- | --- | --- | --- | --- | --- |
| R4-001 | Password-only public SSH | MITIGATE | OPEN | verify, then 90-day review | YES |
| R4-002 | Single VPS/no HA | ACCEPT | ACTIVE | scope/scale triggers; expires by pilot completion | NO |
| R4-003 | Role concentration | ACCEPT | ACTIVE | independence/scale triggers; expires by public evaluation | NO |
| R4-004 | Session-only results | ACCEPT | ACTIVE | pilot/history trigger | NO |
| R4-005 | Full PGN technical logs (superseded) | CLOSED | SUPERSEDED | privacy/logging architecture change | NO |
| R4-006 | No PITR/24-hour loss | ACCEPT | ACTIVE | 90-day/scale/criticality review | NO |
| R4-007 | Single-operator RTO | MITIGATE | OPEN | access/runbook/initial drill evidence | YES |
| R4-008 | Temporary DuckDNS | ACCEPT | ACTIVE | DNS/domain/pilot trigger | NO |
| R4-009 | Missing provisioning/secrets | MITIGATE | OPEN | automatic no-bypass gate passes | YES |
| R4-010 | Runtime/package mismatch | CLOSED | VERIFIED | runtime-policy architecture change | NO |
| R4-011 | Validation not current | CLOSED | VERIFIED | material composition/runtime change | NO |

R4-001 explicitly supersedes the earlier password-only production SSH policy.
Production requires SSH key authentication, disabled password authentication,
disabled direct root login, port 48227, Fail2ban, and rate limiting.

## Readiness axes and remaining blockers

- Decision mapping validation: `PASS` (28/28, invalid 0, conflicts 0).
- Decision package completeness: `PASS` (missing human decisions 0).
- External provisioning completeness: `BLOCKED` (seven mapped domains pending,
  including Hetzner, DuckDNS/TLS, Telegram, R2, GHCR, and production env).
- Deployment executability: `BLOCKED` by R4-001, R4-007, R4-009, external
  provisioning, and incomplete technical go/no-go.
- Closed-pilot launch authorization: `NOT YET GRANTED`.
- Public launch authorization: `NOT GRANTED`.
- Prompt 20-D release: `BLOCKED`.

Production deployment performed: `NO`. Public traffic enabled: `NO`.
External resources provisioned: `NO`.

## R5-R2 authoritative logging-policy revision

Mustafa Bedir authorized the `v1.0-pilot/R5-R2` revision at
`2026-07-31T22:56:09+03:00`. It explicitly supersedes the former acceptance of
full PGN in technical logs. The active policy is metadata-only diagnostics:
full PGN, FEN, raw move lists, game-bearing request bodies and reconstructable
engine input/output are prohibited across logs, traces, monitoring, analytics,
audit records, incident evidence, CI output and test snapshots.

D20R2-016 now excludes raw-game-content logs, D20R2-017 constrains canonical
game hashes to temporary operational use, and D20R2-028 continues to link the
historical R4-005 identity in its now `CLOSED / SUPERSEDED` state. Historical
provenance and the replacement decision are recorded in
`boardtrace-production-logging-policy-supersession-r5-r2.md`.

This revision changes neither provisioning status nor deployment/closed-pilot/
public-launch authorization.

## R5-R2 runtime verification addendum

Clean production-like run `bt20dr5r2-20260731T233207-clean` verified the real
Redis admission/outbox/worker/terminal-cleanup lifecycle, Redis fail-closed
behavior, current migrations and health, encrypted backup/object integrity,
isolated restore, and complete teardown. R4-010 and R4-011 are consequently
`CLOSED / VERIFIED` for repository/runtime scope. Evidence is recorded in
`docs/operations/production-runtime-policy-alignment-r5-r2.md`.

R4-001, R4-007, and R4-009 remain `MITIGATE / OPEN` deployment blockers. No
external provisioning, production deployment, or launch authorization was
performed or inferred.
