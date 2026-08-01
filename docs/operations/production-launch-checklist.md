# BoardTrace Production Launch Checklist

This is an ordered, role-owned checklist for the accepted candidate
`boardtrace-rc20b-23d1973-914c6156`. It is executable only after placeholders
are replaced from approved provider records and every precondition is signed.
It contains no credentials and was not executed by Prompt 20-D.

Notation:

- `<TARGET_...>` is a non-secret approved target value.
- Secret values are injected by the selected secret manager and never placed on
  the command line.
- `<deployment-runner>`, `<edge-control>`, `<monitor-control>`, and
  `<approved-sha256-tool>` are selected provider commands that must be resolved
  and validated before approval. Their unresolved state is a blocker.

# Pre-Freeze

- [ ] **Release Manager** records the approved target account/project, region,
      provider systems, and launch window.
- [ ] **Release Manager** records all actual human approvers and confirms no
      person is silently filling multiple roles.
- [ ] **Engineering** verifies source:

  ```text
  git rev-parse HEAD
  git diff --check
  ```

  Expected HEAD:
  `23d19730e97dd0aa1503202cf3ce04a56f4ff776`.

- [ ] **Release/Security** verifies frozen digests with
      `<approved-sha256-tool>`:

  ```text
  API wheel: b12ef99a2b21e7bd6a1a748f7376acac92737ca14d349555e60274c8e83d2d62
  web tree: 0f8278d80fe603782edab21d1fbc0f9c8a107f91c41ab4cdfc898dc7a3ce2613
  extension tree: 71c9c3249db8fdcddf908ddc1db98b47e91f9f16f777390acc2a0e81416493bb
  Stockfish: 9bde420202717ce083412027fbfb8c5c935b537591d712be8a8a8bae92f6e8d6
  ```

- [ ] **Release Manager** freezes source, dependency, lockfile, migration,
      configuration schema, documentation, and immutable artifacts.
- [ ] **Security** confirms repository/image/registry secret scans are clean.

# Pre-Launch

- [ ] **Operations/SRE** confirms edge, private web/API, private PostgreSQL,
      private authenticated Redis, no worker inbound listener, and no Stockfish
      listener.
- [ ] **Security** confirms exact trusted proxies/hosts/origins, TLS policy,
      HSTS decision, request limits, and rate controls.
- [ ] **Platform Security** confirms every required credential exists only in
      the production secret manager and access audit is enabled.
- [ ] **Database Operations** confirms backup/PITR healthy and the approved
      recovery checkpoint exists.
- [ ] **Operations/SRE** confirms dashboards, alert rules, delivery tests,
      on-call schedules, and communication channels.
- [ ] **Product/Privacy** confirms capacity assumptions, RPO/RTO, retention,
      deletion, and real-user processing approvals.
- [ ] **Release Manager** confirms rollback artifacts and last-known-good
      configuration are available and digest-verified.
- [ ] **Release Manager** conducts T-24h and T-2h hard-gate review. Any missing
      mandatory item is NO-GO.

# Migration

- [ ] **Database Release Operator** puts traffic/new ingestion in the approved
      maintenance state and confirms workers cannot start new work.
- [ ] **Database Operations** verifies checkpoint/PITR evidence.
- [ ] **Database Release Operator** acquires the single migration-executor lock.
- [ ] Run under the migration identity with the database URL injected by the
      secret manager:

  ```text
  uv run --project apps/api alembic -c apps/api/alembic.ini current
  uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
  uv run --project apps/api alembic -c apps/api/alembic.ini current
  ```

  Expected single current/head: `f03a4b5c6d7e`.

- [ ] On any command failure, unknown revision, or mismatched head: stop rollout,
      preserve evidence, keep traffic disabled, declare a data-integrity hold, and
      follow `database-backup-restore.md`. Do not improvise a downgrade.

# Deployment

- [ ] **Release Operator** promotes exact immutable artifacts; no mutable
      `latest` tag or unverified rebuild.
- [ ] **Release Operator** starts private API:

  ```text
  uv run --project apps/api uvicorn boardtrace_api.main:app --host <TARGET_PRIVATE_BIND> --port <TARGET_API_PORT>
  ```

- [ ] **Operations/SRE** verifies:

  ```text
  <http-client> http://<TARGET_PRIVATE_API>/api/v1/health/live
  <http-client> http://<TARGET_PRIVATE_API>/api/v1/health/ready
  ```

- [ ] **Release Operator** starts worker:

  ```text
  uv run --project apps/api celery -A boardtrace_api.worker:celery_app worker --pool=solo --concurrency=1
  ```

- [ ] **Worker Operations** verifies authenticated Redis connectivity, queue
      `boardtrace.analysis.jobs`, Celery control ping, `DisabledBackend`, Stockfish
      checksum, `uciok`, `readyok`, and zero orphan children.
- [ ] **Release Operator** starts private web:

  ```text
  pnpm --filter web start -- --hostname <TARGET_PRIVATE_BIND> --port <TARGET_WEB_PORT>
  ```

- [ ] **Operations/SRE** verifies private web readiness and exact artifact
      identity.
- [ ] **Edge Operator** keeps public traffic disabled until all smoke/security/
      observability gates pass.

# Smoke

- [ ] Use only a synthetic/operator-owned account and synthetic completed game.
- [ ] Verify health and authentication.
- [ ] Verify extension pairing and one-time exchange.
- [ ] Verify completed-game ingestion creates one game/job/outbox path.
- [ ] Verify real worker/native Stockfish produces one complete current run.
- [ ] Verify the sole server-owned transition reaches `ANALYSIS_AVAILABLE`.
- [ ] Verify owner delivery, generic non-owner denial, and no forbidden internal
      DTO fields.
- [ ] Verify live, unfinished, unverified, missing-moves, and missing-payload-hash
      cases create zero job/outbox/task/Stockfish/public delivery.
- [ ] Verify pending outbox, active jobs, active leases, and orphan Stockfish
      children return to zero.

# Security

- [ ] **Security** verifies TLS, certificate chain, HTTPS redirect, HSTS
      decision, CSP, anti-framing, `nosniff`, referrer, and permissions policies.
- [ ] Verify exact Host, origin, trusted proxy, forwarded-header, method,
      request-body, and header-size controls.
- [ ] Verify secure `HttpOnly`, `SameSite=Strict`, path-root cookies and CSRF
      denial.
- [ ] Verify production rate thresholds, privacy-safe keys, `429`,
      `Retry-After`, backend-failure policy, recovery, and non-bypass behavior.
- [ ] Verify PostgreSQL/Redis are not publicly routable and no secret reaches
      browser/extension/logs.

# Observability

- [ ] **Operations/SRE** verifies all required metrics and dashboards are fresh.
- [ ] Trigger approved synthetic test signals for critical alerts and confirm
      primary, secondary, recovery, and delivery-failure monitoring.
- [ ] Verify no user/game/job/run/request/token/raw exception labels.
- [ ] Verify backup/PITR, queue/outbox, worker/lease, Stockfish, auth, delivery,
      database, Redis, and edge signals.

# Traffic Enablement

- [ ] **Release Manager** confirms every hard gate is GO and records attributable
      approvals.
- [ ] **Edge Operator** enables only the approved canary/limited audience or
      maintenance-window cutover using `<edge-control>`.
- [ ] If canary percentage/duration is not approved, traffic remains disabled.

# Stabilization

- [ ] Observe for the approved minimum duration; the duration is currently
      unresolved.
- [ ] Require no security/data-integrity alert, no monitoring blind state, no
      unexpected `5xx`, no unacceptable latency, bounded queue age/depth, zero
      stale leases/outbox, healthy DB/Redis, available worker, and zero Stockfish
      orphan/failure storm.
- [ ] Capture safe aggregate evidence and compare to approved thresholds.

# Go/No-Go

- [ ] **Release Manager** reads every hard gate and risk record.
- [ ] Security, Database, and Privacy owners exercise blocking authority for
      their invariants.
- [ ] Record GO only with all mandatory human approvals and no unresolved
      hard-gate blocker.
- [ ] Current Prompt 20-D decision: **NO-GO**.

# Rollback

- [ ] **Release Manager/Security/Database Owner** may declare rollback or hold.
- [ ] **Edge Operator** stops/limits traffic.
- [ ] **Application Operator** stops new ingestion/scheduling and drains or
      freezes queue according to authoritative PostgreSQL state.
- [ ] **Release Operator** deploys prior compatible digest-pinned API/worker/web
      artifacts and last-known-good configuration.
- [ ] Do not destructively downgrade PostgreSQL by default; prefer forward fix
      or approved restore/PITR to a new target under a data-integrity hold.
- [ ] Verify readiness, synthetic smoke, owner/non-owner boundary, queue/outbox/
      leases, worker/Stockfish, and data-integrity sentinels.
- [ ] **Communications Owner** publishes rollback/degraded-service notice.

# Closure

- [ ] Confirm public/limited traffic state and final release identity.
- [ ] Confirm queue/outbox/jobs/leases/Stockfish children are safe.
- [ ] Confirm incident/hold status, monitoring, backups, and rollback retention.
- [ ] Store privacy-minimized evidence and approval timestamps.
- [ ] Schedule post-launch/rollback review and corrective owners.
- [ ] Revoke temporary/break-glass access and review its audit trail.

# Command Ownership

| Command/action                       | Authority                              | Environment              | Expected output                    | Failure action       | Rollback action                 | Evidence             |
| ------------------------------------ | -------------------------------------- | ------------------------ | ---------------------------------- | -------------------- | ------------------------------- | -------------------- |
| `git rev-parse HEAD` / digest checks | Release/Security                       | trusted build workspace  | frozen identities match            | NO-GO                | retain prior artifact           | revision/digest list |
| Alembic current/upgrade/current      | Database Release Operator              | private migration runner | one `f03a4b5c6d7e`                 | stop/data hold       | forward fix or approved restore | sanitized exit/head  |
| Uvicorn start                        | Application Operator                   | private API runtime      | liveness/readiness pass            | stop component       | prior compatible API            | deployment event     |
| Celery solo worker start             | Worker Operator                        | private worker runtime   | ping/queue/engine pass             | stop worker          | prior compatible worker         | ping/config event    |
| Next.js start                        | Web Operator                           | private web runtime      | private HTTP ready                 | stop web             | prior compatible web            | readiness event      |
| Edge traffic control                 | Edge Operator with Release approval    | selected edge            | approved audience only             | keep/return disabled | route to prior release          | edge change event    |
| Rollback declaration                 | Release Manager; Security/DB may block | incident channel         | traffic limited and owners engaged | escalate incident    | n/a                             | UTC decision log     |

# Unresolved Placeholders

The target/provider commands, private hostnames, account, region, ports,
registry, monitoring, alert, edge, backup/PITR, status-channel, staffing,
threshold, duration, canary, and launch-window placeholders are unresolved.
This checklist is therefore created but not launch-executable.

# Prompt 20-D-R1 Reconciliation

- [x] Bind remediation run `bt20dr1-1785276698-550f3a` to evidence
      `boardtrace-readiness20dr1-23d1973-3eec336b`.
- [x] Preserve accepted RC/source/artifact identities.
- [x] Create explicit ownership, capacity, retention, monitoring/on-call,
      backup/PITR, artifact/provenance, and sign-off records.
- [ ] Select and approve production target, account/project, region, and
      mandatory providers.
- [ ] Approve forecast, sizing, rate controls, backup/PITR/RPO/RTO,
      retention/deletion, and support/communication policies.
- [ ] Assign actual primary/secondary on-call and incident roles.
- [ ] Record eight valid organizational sign-offs and an approved launch
      window.
- [ ] Close or validly accept all mandatory High/Medium risks.

Current R1 decision: **NO-GO / BLOCKED**. This checklist does not authorize
provisioning, deployment, promotion, or public traffic.

# Prompt 20-D-R2 Decision-Package Gate

- [x] Create R2 run/evidence identity.
- [x] Validate the supplied material as procedural rather than approval
      evidence.
- [x] Record 28 expected, 0 located, 0 valid, and 28 missing decision domains.
- [x] Preserve all unresolved decision placeholders.
- [ ] Receive and validate an authoritative, scoped, timestamped decision
      package.

Current R2 decision: **NO-GO / BLOCKED**.

# Prompt 20-D-R3 Authoritative Decision Gate

- [x] Integrate v1.0-pilot Markdown and provenance.
- [x] Map and evaluate all 28 R2 identifiers.
- [x] Validate mapping: 12 resolved, 7 pending provisioning, 16 missing, 0
      invalid, 0 conflicts.
- [x] Preserve closed-pilot and public-launch authorization as not granted.
- [ ] Resolve D20R2-012, 014, 016-028.
- [ ] Provision and verify Hetzner/VPS, DuckDNS/TLS, Telegram, Cloudflare R2,
      GHCR/CI, age keys, and the final production environment.
- [ ] Reconcile approved session-only deletion, queue/cancellation, PGN
      logging, concurrency, and timeout behavior with production source.
- [ ] Complete production-like composition, smoke, security, backup/restore,
      monitoring/alert, rollback, and staffed go/no-go evidence.

Decision mapping validity does not make this checklist executable. Current
deployment executability: **BLOCKED**. Closed-pilot launch: **NOT YET
GRANTED**. Public launch: **NOT GRANTED**.
