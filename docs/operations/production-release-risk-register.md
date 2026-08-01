# BoardTrace Production Release Risk Register

This register is the Prompt 20-D launch-governance record for accepted release
candidate `boardtrace-rc20b-23d1973-914c6156`. It records the actual state as of
2026-07-29. No open risk is implicitly accepted, and no entry authorizes
production deployment or public traffic.

## Decision Summary

Prompt 20-D is blocked because the production target, providers, business/load
forecast, accountable humans, launch window, and activated production controls
are not evidenced. Critical security findings are zero, but mandatory
preparation and organizational gates remain open.

## Risk Records

### R-20D-001 — Production target and provider selection

- Risk ID: `R-20D-001`
- Source: Prompt 20-D target discovery
- Severity: HIGH readiness risk
- Description: cloud account/project, region, runtime platform, database,
  Redis, edge/TLS, monitoring, alerting, secret-manager, registry, and CI/CD
  providers are unknown.
- Likelihood: certain in the current evidence
- Impact: architecture cannot be validated against an actual platform and
  production deployment must not begin.
- Affected component: entire production topology
- Launch relevance: automatic NO-GO
- Mitigation: select the target and providers, record account/region and
  platform capabilities, and obtain owner approval.
- Owner: Release Manager with Operations/SRE
- Status: OPEN / BLOCKING
- Acceptance authority: not eligible for risk acceptance; target evidence is a
  mandatory gate.
- Review/expiry: review when provider records are supplied; no acceptance
  expiry applies.
- Rollback/incident trigger: any target mismatch after selection invalidates
  Prompt 20-D evidence.
- Decision: BLOCKED

### R-20D-002 — Capacity forecast and sizing

- Risk ID: `R-20D-002`
- Source: Prompt 20-B capacity boundary / Prompt 20-D
- Severity: HIGH readiness risk
- Description: initial users, DAU, peak concurrency, games/user, jobs/hour,
  average move count, peak ingestion, and target drain window are unknown.
- Likelihood: certain in the current evidence
- Impact: API/web/worker/database/Redis sizing and scaling triggers cannot be
  approved.
- Affected component: runtime capacity, especially serialized
  worker/Stockfish throughput
- Launch relevance: automatic NO-GO
- Mitigation: Product supplies bounded forecasts; Operations converts them to
  a proposed envelope and validates it in an approved pre-production dry run.
- Owner: Product Owner and Operations/SRE Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Business/Executive Owner plus Operations/SRE; no
  acceptance recorded.
- Review/expiry: at forecast delivery and before launch-window approval
- Rollback/incident trigger: queue age or resource saturation beyond the
  approved envelope.
- Decision: BLOCKED

### R-20D-003 — Monitoring and alert delivery inactive

- Risk ID: `R-20D-003`
- Source: Prompt 19-B, Prompt 20-C, Prompt 20-D
- Severity: HIGH operational risk
- Description: the production collector, storage, dashboards, alert transport,
  and synthetic alert delivery are not selected, provisioned, activated, or
  tested.
- Likelihood: certain before provisioning
- Impact: blind deployment, delayed detection, and unverifiable stabilization
- Affected component: all production services
- Launch relevance: automatic NO-GO
- Mitigation: select platform, configure the required metric/alert inventory,
  test delivery and recovery, and retain safe evidence.
- Owner: Operations/SRE Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Operations/SRE and Release Manager; not accepted.
- Review/expiry: before T-24h
- Rollback/incident trigger: monitoring blind state during deployment or
  stabilization.
- Decision: BLOCKED

### R-20D-004 — On-call and incident ownership pending

- Risk ID: `R-20D-004`
- Source: Prompt 19-C and Prompt 20-D
- Severity: HIGH organizational risk
- Description: no actual primary, secondary, incident commander, security, or
  data-integrity on-call humans and contact methods are evidenced.
- Likelihood: certain in current evidence
- Impact: alerts and rollback decisions have no accepted human recipient.
- Affected component: incident response and launch governance
- Launch relevance: automatic NO-GO
- Mitigation: assign real people/schedules and confirm coverage, handoff,
  escalation, and contact paths.
- Owner: Operations/SRE Owner and Release Manager
- Status: OPEN / BLOCKING
- Acceptance authority: Business/Executive Owner; not accepted.
- Review/expiry: before go/no-go meeting scheduling
- Rollback/incident trigger: unreachable primary or secondary during the
  staffing window.
- Decision: BLOCKED

### R-20D-005 — Production rate controls incomplete

- Risk ID: `R-20D-005`
- Source: Prompt 19-C and Prompt 20-D
- Severity: HIGH security/availability risk
- Description: endpoint thresholds and enforcement provider are not approved;
  production enforcement and backend-failure tests are inactive.
- Likelihood: certain before provider selection
- Impact: authentication, pairing, ingestion, scheduling, polling, and health
  abuse may be unbounded.
- Affected component: edge and public request surfaces
- Launch relevance: automatic NO-GO
- Mitigation: approve privacy-safe keys and exact values, activate enforcement,
  verify `429`/`Retry-After`, recovery, and non-bypass behavior.
- Owner: Security Owner with Operations/SRE Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Security Owner and Release Manager; not accepted.
- Review/expiry: before T-24h
- Rollback/incident trigger: limiter loss, bypass, or silent unlimited fallback.
- Decision: BLOCKED

### R-20D-006 — Backup, PITR, RPO, and RTO not approved

- Risk ID: `R-20D-006`
- Source: Prompt 19-A and Prompt 20-D
- Severity: HIGH data-recovery risk
- Description: production database provider, backup schedule/retention, PITR
  capability/window, storage identity, and organizational RPO/RTO are unknown.
- Likelihood: certain before provider and business decisions
- Impact: data-loss and recovery exposure cannot be bounded.
- Affected component: PostgreSQL and recovery operations
- Launch relevance: automatic NO-GO
- Mitigation: select provider, approve RPO/RTO, activate encrypted backup/PITR
  monitoring, and complete an isolated time-target restore rehearsal.
- Owner: Database Operations, Data/Privacy Owner, Business/Executive Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Business/Executive and Data/Privacy; not accepted.
- Review/expiry: before launch-window approval
- Rollback/incident trigger: missing/stale backup, unhealthy PITR, checksum or
  restore validation failure.
- Decision: BLOCKED

### R-20D-007 — Retention and deletion governance incomplete

- Risk ID: `R-20D-007`
- Source: Prompt 19-C and Prompt 20-D
- Severity: HIGH privacy readiness risk
- Description: retention durations, legal/business basis approval, deletion
  request workflow, backup re-deletion, audit exceptions, and privacy contact
  are not approved or implemented.
- Likelihood: certain in current evidence
- Impact: real-user processing could violate approved privacy governance.
- Affected component: account, session, game, analysis, audit, logs, and backups
- Launch relevance: automatic NO-GO
- Mitigation: obtain counsel/business decisions, implement and test the
  server-owned deletion workflow, and approve hold/backup handling.
- Owner: Data/Privacy Owner with Product Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Data/Privacy and Business/Executive; not accepted.
- Review/expiry: before any real-user onboarding
- Rollback/incident trigger: deletion request cannot be completed or unlawful
  retention is suspected.
- Decision: BLOCKED

### R-20D-008 — Organizational sign-offs and launch window pending

- Risk ID: `R-20D-008`
- Source: Prompt 20-C and Prompt 20-D
- Severity: HIGH governance risk
- Description: actual human approvals, role assignments, go/no-go meeting
  authority, and launch window are absent.
- Likelihood: certain in current evidence
- Impact: no authorized deployment decision can be made.
- Affected component: release governance
- Launch relevance: automatic NO-GO
- Mitigation: collect attributable approval evidence and select a staffed
  window with rollback deadline.
- Owner: Release Manager and Business/Executive Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Business/Executive Owner; not accepted.
- Review/expiry: before scheduling deployment
- Rollback/incident trigger: missing approver or staffing at T-24h/T-2h.
- Decision: BLOCKED

### R-20D-009 — Prompt 20-B owner-read timeout

- Risk ID: `R-20D-009` / source finding `F-20B-LOW-01`
- Source: Prompt 20-B
- Severity: LOW
- Description: one read-only owner request timed out at 15 seconds; later reads
  and final integrity checks succeeded.
- Likelihood: observed once in 490 owner reads; production frequency unknown
- Impact: degraded owner experience; no accepted-work loss or state mutation
- Affected component: owner analysis delivery
- Launch relevance: must be monitored and dispositioned in capacity approval
- Mitigation: latency histogram, 15-second timeout counter, dependency
  correlation, support retry guidance, and review before production sizing
  approval.
- Owner: Operations/SRE Owner
- Status: ACCEPTED FOR CONTROLLED STAGING ONLY / OPEN FOR PRODUCTION
- Acceptance authority: prior controlled-staging Operations decision; no
  production acceptance.
- Review/expiry: 2026-08-28 or earlier at production target selection
- Rollback/incident trigger: repeated timeout, elevated p99, or correlated
  dependency degradation.
- Decision: NOT A CURRENT SECURITY BLOCKER; PRODUCTION DISPOSITION PENDING

### R-20D-010 — Deployment CSP hardening

- Risk ID: `R-20D-010` / source condition `R-20C-INFO-01`
- Source: Prompt 20-C
- Severity: MEDIUM deployment hardening risk
- Description: nonce-compatible production CSP and actual edge header behavior
  are not verified on a selected provider.
- Likelihood: certain until edge selection/test
- Impact: weaker browser defense in depth
- Affected component: edge/web
- Launch relevance: mandatory edge/TLS validation gate
- Mitigation: select edge, implement a Next.js-compatible CSP without unsafe
  broadening, test framing/script behavior, and record security approval.
- Owner: Security Owner and Engineering Owner
- Status: OPEN / BLOCKING FOR PUBLIC LAUNCH
- Acceptance authority: Security Owner; not accepted.
- Review/expiry: before edge activation approval
- Rollback/incident trigger: missing/relaxed CSP or script execution outside
  the allowlist.
- Decision: BLOCKED

### R-20D-011 — Artifact registry and promotion provenance

- Risk ID: `R-20D-011`
- Source: Prompt 20-D
- Severity: HIGH supply-chain readiness risk
- Description: production registry, builder identity, immutable promotion,
  signing/attestation, and retention controls are unknown.
- Likelihood: certain before CI/CD selection
- Impact: accepted digests may not be the artifacts deployed.
- Affected component: API, worker, web, extension, Stockfish
- Launch relevance: automatic NO-GO
- Mitigation: select registry/CI, upload immutable accepted artifacts or perform
  verified reproducible builds, verify digest at deploy, retain prior
  compatible artifacts.
- Owner: Release Manager with Security Owner
- Status: OPEN / BLOCKING
- Acceptance authority: Release Manager and Security Owner; not accepted.
- Review/expiry: before artifact promotion
- Rollback/incident trigger: digest mismatch, mutable tag, missing provenance,
  or unavailable rollback artifact.
- Decision: BLOCKED

### R-20D-012 — Support and status channels not selected

- Risk ID: `R-20D-012`
- Source: Prompt 20-D
- Severity: MEDIUM operational risk
- Description: support owner, status channel, incident notice path, and launch
  communication channels are not evidenced.
- Likelihood: certain in current evidence
- Impact: users and operators may receive delayed or inconsistent guidance.
- Affected component: support and communications
- Launch relevance: mandatory go/no-go gate
- Mitigation: select channels, assign actual owners, approve templates, and
  rehearse deployment/rollback notices.
- Owner: Support Owner and Release Manager
- Status: OPEN / BLOCKING
- Acceptance authority: Product Owner and Release Manager; not accepted.
- Review/expiry: before T-24h
- Rollback/incident trigger: no reachable status/support channel at deployment
  start.
- Decision: BLOCKED

## Acceptance Review

Accepted production risks: zero. Implicit acceptances: zero. The Prompt 20-B
Low finding remains accepted only for its completed controlled-staging scope.
All other entries require resolution or explicit accountable approval under the
project's risk policy; mandatory target, security, privacy, recovery, and human
authority gates are not waivable by this document.

## Prompt 20-D-R1 Reconciliation

Run `bt20dr1-1785276698-550f3a` supplied no authoritative closure or acceptance
evidence. All 12 records remain open:

- Critical: 0
- High: 9
- mandatory Medium: 2
- Low: 1
- implicit acceptances: 0

No severity was reduced, no owner was converted from a role placeholder to an
actual assignee, and no review/expiry date was invented. The release remains
`BLOCKED`.

## Prompt 20-D-R2 Decision Intake

No closure or acceptance record was located. Risk changes: zero; rejected or
invalid acceptances: zero; implicit acceptances: zero. All 12 risk records keep
their R1 status and severity. Decision domain `D20R2-028` remains missing.

## Prompt 20-D-R3 Risk Reconciliation

The authoritative package supplies real mitigation decisions without proving
activation or closing deployment gates:

- R-20D-001: provider/region/topology decisions exist; account/resources remain
  unprovisioned.
- R-20D-002: pilot forecast and CX33/concurrency/queue decisions exist;
  production implementation and capacity certification remain unverified.
- R-20D-003: Uptime Kuma/Telegram policy exists; monitoring and alert delivery
  remain unprovisioned and untested.
- R-20D-004: Mustafa Bedir is operational owner, but primary/secondary and
  incident roles/coverage remain missing.
- R-20D-005: concurrency/queue controls exist; the complete R2 rate-limit
  contract remains missing.
- R-20D-006: backup/RPO/RTO/restore decisions exist; R2/age resources and tests
  remain unprovisioned.
- R-20D-007: retention/deletion values exist; Privacy/Data approval and source
  compatibility remain unresolved.
- R-20D-008: package owner and conditional launch authority exist; role-scoped
  sign-offs and an actual launch window remain missing.
- R-20D-009: no owner/review disposition was supplied for the accepted
  owner-read timeout.
- R-20D-010: deployment CSP remains a technical condition.
- R-20D-011: GHCR/GitHub Actions are selected; provenance, signing, immutable
  promotion, credentials, and publication remain incomplete.
- R-20D-012: a support group is selected; status/internal incident channels and
  playbook governance remain incomplete.

The password-only, internet-reachable SSH choice is recorded as an acknowledged
High security risk, but its acceptance lacks the review date and expiry required
by the risk policy. D20R2-028 therefore remains missing; no risk is silently
closed or accepted.

## Prompt 20-D-R4 authoritative risk register

The R3 open-risk narrative remains historical. R4 replaces its missing
D20R2-028 disposition with eleven structured records in the authoritative JSON.
All are owned by Mustafa Bedir and recorded at `2026-07-31T16:40:14+03:00`.

| ID     | Risk                       | Disposition/state | Review or expiry                  | Blocker |
| ------ | -------------------------- | ----------------- | --------------------------------- | ------- |
| R4-001 | password-only public SSH   | MITIGATE/OPEN     | verify then every 90 days         | YES     |
| R4-002 | single VPS/no HA           | ACCEPT/ACTIVE     | scope triggers; pilot expiry      | NO      |
| R4-003 | eight-role concentration   | ACCEPT/ACTIVE     | independence/scale triggers       | NO      |
| R4-004 | session-only results       | ACCEPT/ACTIVE     | pilot/history trigger             | NO      |
| R4-005 | 24-hour full-PGN logs      | ACCEPT/ACTIVE     | every 90 days/architecture change | NO      |
| R4-006 | no PITR/24-hour RPO        | ACCEPT/ACTIVE     | every 90 days/scale trigger       | NO      |
| R4-007 | single-operator RTO        | MITIGATE/OPEN     | access/runbook/drill evidence     | YES     |
| R4-008 | temporary DuckDNS          | ACCEPT/ACTIVE     | DNS/domain/pilot trigger          | NO      |
| R4-009 | missing external inputs    | MITIGATE/OPEN     | no-bypass gate passes             | YES     |
| R4-010 | runtime/package mismatch   | MITIGATE/OPEN     | fixes and tests pass              | YES     |
| R4-011 | stale integration evidence | MITIGATE/OPEN     | current validation passes         | YES     |

No mitigation is claimed complete. Password-only production SSH is
superseded: keys are required and password login must be disabled and verified.

## Prompt 20-D-R5 repository implementation status

R5 run `bt20dr5-1785507944-23d197` preserves the R4 dispositions and records
implementation evidence without closing externally unverified controls.

| ID     | R5 implementation state                             | Verification                                                                          | Deployment blocker |
| ------ | --------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------ |
| R4-001 | IMPLEMENTED_PENDING_HOST_VERIFICATION               | repository validator/tests PASS; host not tested                                      | YES                |
| R4-007 | READY_FOR_PROVISIONING                              | runbook/dispatcher/static tests PASS; account and drill absent                        | YES                |
| R4-009 | REPOSITORY_IMPLEMENTED / EXTERNAL_PREFLIGHT_BLOCKED | fixture PASS; empty real environment fails closed                                     | YES                |
| R4-010 | PARTIAL / BLOCKED                                   | several focused controls pass; queue, terminal coverage and PGN sink incomplete       | YES                |
| R4-011 | PARTIAL / BLOCKED                                   | current core Docker composition PASS; full queue/failure/backup/restore suite not run | YES                |

Evidence: `docs/operations/production-policy-runtime-alignment-r5.md` and
`docs/operations/production-runtime-policy-traceability-r5.md`. Active
deployment-blocking MITIGATE risks remain five; no risk is closed.

## R5-R1 runtime and recovery addendum

RUN_ID `bt20dr5r1-1785511988-23d1973` passed the extended production-like
Docker harness, including Redis bounded-FIFO controller semantics,
Redis-unavailable fail-closed/recovery, age-encrypted logical backup, local
S3-compatible object size/checksum verification and isolated PostgreSQL
restore. Complete teardown was independently confirmed.

R4-011 improves from core-only evidence to `PARTIAL / BLOCKED WITH EXTENDED
DOCKER PASS`. It is not closed because the controller is not yet integrated
with the public ingestion/outbox lifecycle and the timeout/cancellation/
queue-expiry/worker-loss cleanup matrix is incomplete. R4-010 remains
`PARTIAL / BLOCKED`; the 24-hour full-PGN requirement also conflicts with the
repository's secure-logging invariant and was not silently implemented.

Durable evidence:
`docs/operations/production-runtime-disaster-recovery-r5-r1.md`.

## R5-R2 authoritative closure addendum

R5-R2 explicitly supersedes the 24-hour full-PGN policy and integrates the
Redis admission and terminal lifecycle into the real API/outbox/worker paths.
Clean run `bt20dr5r2-20260731T233207-clean` passed the complete
production-like harness and teardown.

| ID     | R5-R2 disposition/state | Evidence                                                      | Deployment blocker |
| ------ | ----------------------- | ------------------------------------------------------------- | ------------------ |
| R4-005 | CLOSED / SUPERSEDED     | metadata-only authoritative revision and unsafe-content tests | NO                 |
| R4-010 | CLOSED / VERIFIED       | real admission/outbox/terminal integration and policy tests   | NO                 |
| R4-011 | CLOSED / VERIFIED       | current Docker queue/failure/backup/restore run               | NO                 |
| R4-001 | MITIGATE / OPEN         | real host verification absent                                 | YES                |
| R4-007 | MITIGATE / OPEN         | secondary access and staffed drill absent                     | YES                |
| R4-009 | MITIGATE / OPEN         | external resources and no-bypass production preflight absent  | YES                |

Current counts are five active ACCEPT risks, three open MITIGATE risks, three
closed risks, and three deployment blockers. The closure evidence is
`docs/operations/production-runtime-policy-alignment-r5-r2.md`. It does not
claim host/operator mitigation, deployment executability, or launch approval.

## R6 Mode A qualification addendum

R6 reran all 15 previously incomplete R5-R2 tests: 10 temp-directory-dependent
tests and five PostgreSQL transaction/concurrency tests passed. The production
environment contract was corrected to reject the superseded PGN-retention key
and require metadata-only/no-raw-game logging. R4-010 and R4-011 remain
`CLOSED / VERIFIED`. A UUID/UCI-pattern false positive discovered during R6
stability testing was corrected without weakening game-content detection;
focused regression tests, corrected full Docker run
`bt20dr6-20260801T025200-fixed2`, and five consecutive integrated lifecycle
iterations pass. Runtime audit-adapter failures are now non-propagating.

No Mode B authorization was supplied. R4-001 is
`READY_FOR_HOST_VERIFICATION / BLOCKED`; R4-007 is
`READY_FOR_PROVISIONING / BLOCKED`; R4-009 is
`IMPLEMENTED_PENDING_REAL_VALUES / BLOCKED`. Their machine risk dispositions
remain `MITIGATE / OPEN`, and external mutation count is zero. Evidence:
`docs/operations/production-provisioning-host-readiness-r6.md`.
