# BoardTrace Production Logging Policy Supersession — R5-R2

## Decision identity

- Authority: Mustafa Bedir
- Intake timestamp: `2026-07-31T22:56:09+03:00`
- Package version: `v1.0-pilot/R5-R2`
- Prior package: `v1.0-pilot/R4`
- Source SHA-256:
  `e58bb559ab3eabeb650a8ac01f1fb6b368ae5ecbced02ebcfde986b98566df91`
- Affected decisions: D20R2-016, D20R2-017 and D20R2-028
- Affected risk: R4-005

## Superseded decision

The former policy accepted retention of full PGN in technical logs for up to
24 hours, limited access to Mustafa Bedir through an SSH-tunnel-only log viewer,
and required automatic deletion.

That policy is `SUPERSEDED`. It is retained here only as historical provenance
and cannot be selected as active production policy.

## Replacement decision

The active production policy is `METADATA_ONLY` diagnostic logging. Full PGN,
FEN, raw move lists, request bodies containing game data, and engine input or
output containing reconstructable game state are prohibited from general logs,
technical logs, traces, monitoring, analytics, audit records, rate-limit logs,
incident records, CI output and test snapshots.

Only narrowly enumerated operational metadata may be emitted: bounded
correlation/job/task/outbox identifiers; masked identities and IP addresses;
source/acquisition identifiers where policy permits; canonical cryptographic
checksums; categorical errors, lifecycle/queue/cleanup outcomes and live-game
guard decisions; timestamps, durations, component names and safe versions.
Metadata must not permit practical game reconstruction or become analysis
history or a permanent user profile.

Dozzle remains an SSH-tunnel-only general container-log viewer. It is not a raw
game-content store and must never display prohibited content.

## Reason and compatibility

The revision removes unnecessary privacy exposure and resolves the conflict
with `AGENTS.md`, which requires data minimization and prohibits backend logs
from containing request bodies, screenshots, FEN values, credentials or
secrets. It does not weaken that rule or reinterpret the prior decision
silently.

Affected implementation areas are the structured logging formatter, analysis
audit events, API/worker/outbox/cleanup logs, validation tests, traceability and
risk reporting. The revision grants no deployment or launch authorization and
does not change external provisioning status.
