# BoardTrace Production Recovery Drill Checklist

Run before pilot deployment, every 90 days, and after material infrastructure
change. R5 supplies the template only; it does not claim a human drill.

## Preconditions

- [ ] Participants: Mustafa Bedir and Ahmet Bedir
- [ ] Isolated production-like environment; no production credentials/data
- [ ] Previous-known-good immutable image recorded
- [ ] Test-only encrypted backup and restore target available
- [ ] User-safe communication draft prepared
- [ ] Start time and expected four-hour RTO recorded

## Scenarios

- [ ] Stopped API container: inspect, restart, health-check
- [ ] Failed worker: stop intake if needed, restart, verify job boundary
- [ ] Redis unavailable: verify fail-closed 503 and `Retry-After: 60`
- [ ] Rollback: identify and start previous-known-good image without building
- [ ] Disk threshold: verify restricted mode and manual reactivation boundary
- [ ] Health: verify minimum anonymous response and private dependency checks
- [ ] Communications: perform primary-to-secondary handoff and closure draft
- [ ] Backup: verify encrypted object metadata; stop before unauthorized restore

## Evidence record

- Date/time and timezone:
- Environment identity:
- Participants and roles:
- Scenario:
- Initial state:
- Commands/actions (secret-safe):
- Exit codes and observed result:
- Elapsed time:
- Success criteria and outcome:
- Deviations:
- Follow-up actions, owner, target date:
- Evidence paths/hashes:
- Approvals: Mustafa approval / Ahmet acknowledgement:

The drill fails if a prohibited action is required, the secondary operator can
escape the dispatcher, evidence contains secrets/raw game data, recovery
exceeds the approved boundary, or the live-game invariant cannot be proven.

## Local rehearsal entry point

Run `scripts/run_production_like_validation.ps1` from the repository root for
the isolated technical rehearsal. It validates the core composition, Redis
queue-controller policy and fail-closed recovery, encrypted local-S3 upload,
object integrity and isolated database restore, then removes its test resources.
This automated rehearsal does not replace the staffed production recovery drill.
