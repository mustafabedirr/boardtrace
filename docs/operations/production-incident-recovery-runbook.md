# BoardTrace Production Incident and Recovery Runbook

## Authority and activation

Mustafa Bedir is primary on-call and incident commander. Ahmet Bedir becomes
secondary operator only when repeated direct contact attempts through the
documented private contact path receive no response and the incident response
target would otherwise be missed. Record every attempt and activation time.

Ahmet may run only `sudo /usr/local/sbin/boardtrace-recovery` with one of:
`status`, `stop`, `restart`, `rollback`, or `health`. He may not deploy a new
release, change architecture or policy, accept risk, expand the pilot, approve
launch, access secrets, or obtain an unrestricted root shell. Stop and escalate
if an action falls outside the dispatcher or requires a database restore.

## Severity and response start

| Severity | Examples | Start target | Required posture |
| --- | --- | --- | --- |
| SEV-1 | security issue, possible live-game engine output, total outage | 15 minutes | fail closed; stop new analyses; isolate or stop service |
| SEV-2 | worker/queue failure or serious analysis degradation | 1 hour | restrict intake and recover safely |
| SEV-3 | limited defect or low-impact issue | 24 hours | contain and schedule remediation |

Never reactivate after a SEV-1 until remediation and verification preserve
`NO ENGINE OUTPUT DURING LIVE GAMES`.

## Recovery sequence

1. Open an incident record; note UTC/local time, operator, severity, and impact.
2. Run `sudo /usr/local/sbin/boardtrace-recovery status`. Capture container
   names/status only; do not capture environment or raw game data.
3. For Redis unavailable, stop new analysis intake. Do not bypass fail-closed
   behavior or replace shared counters with process-local state.
4. For disk at or above 90%, keep analysis intake in restricted mode. Free
   only documented disposable data; never delete database volumes or backups.
5. For a stopped application/worker, run `restart`, then `health`. If the same
   fault repeats, stop and escalate.
6. For a confirmed bad release, verify `/opt/boardtrace/previous-known-good.env`
   is root-owned, identifies the previously verified immutable image, and is
   not the current failed image. Run `rollback`, then `health` and `status`.
7. Confirm the minimum health response without version, dependency, database,
   infrastructure, or configuration details. Confirm analysis remains locked
   for live/unknown/stale game state.
8. Check that the most recent encrypted backup object has recorded existence,
   size, and checksum verification. Ahmet may not decrypt or restore it.
9. Database restore is an incident-commander decision. Stop and escalate to
   Mustafa; preserve the failed state and evidence.

## Communication and evidence

Mustafa leads communications; Ahmet is fallback while Mustafa is unreachable.
Use the BoardTrace Pilot Telegram group for user-safe notices, never secrets,
raw PGN, exploit detail, personal data, or infrastructure-sensitive detail.
SEV-1 initial notice is due within 30 minutes and updates every 60 minutes;
SEV-2 within two hours and every four hours. Closure includes impact, start/end,
current status, and user action.

Record commands, exit codes, timestamps, observed state, affected services,
decision points, rollback image digest, validation outcome, deviations, and
follow-up owner/date. Do not record authorization headers, environment values,
database URLs, tokens, full IPs, full user identifiers, FEN, moves, or PGN.

## Stop conditions

Stop and escalate when the live-game invariant may be breached, a command is
outside the allowlist, recovery repeats without improvement, data integrity is
uncertain, restore/decryption is needed, required evidence cannot be preserved,
or access boundaries do not match this runbook.

## Host access design and provisioning

- Separate named Linux accounts `mustafa` and `ahmet`; never shared credentials.
- Distinct SSH public keys; private keys are never copied to the server/repo.
- Key-only port 48227; password, keyboard-interactive, and root login disabled.
- Ahmet's sudoers entry permits only the root-owned recovery dispatcher.
- Authentication and sudo/dispatcher activity remains auditable.
- Dozzle and Uptime Kuma bind to localhost and are reached only through an
  authorized SSH tunnel.

Provisioning order: create account, install public key, validate a second login,
install root-owned dispatcher/sudoers policy, validate with `visudo`, apply SSH
hardening, run `sshd -t` and `sshd -T`, reload while retaining the bootstrap
session, then independently verify port 48227. No real account is created by R5.
