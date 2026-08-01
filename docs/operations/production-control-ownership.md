# BoardTrace Production Control Ownership

Run `bt20dr1-1785276698-550f3a` records role ownership without inventing people
or provider teams.

| Control               | Configuration owner | Operational owner  | Approval owner               | Escalation owner       | Current stage | Next-stage action                                        |
| --------------------- | ------------------- | ------------------ | ---------------------------- | ---------------------- | ------------- | -------------------------------------------------------- |
| target/account/region | Operations/SRE      | Operations/SRE     | Release Manager              | Business/Executive     | UNKNOWN       | select and approve actual target                         |
| runtime platform      | Engineering         | Operations/SRE     | Engineering and Operations   | Release Manager        | UNKNOWN       | select provider and validate capability                  |
| PostgreSQL            | Data/DBA            | Operations/SRE     | Data and Operations          | Incident Commander     | UNKNOWN       | select provider and approve HA/backup contract           |
| Redis                 | Engineering         | Operations/SRE     | Engineering and Operations   | Incident Commander     | UNKNOWN       | select provider and approve private non-durable contract |
| edge/DNS/TLS          | Operations/SRE      | Operations/SRE     | Security and Operations      | Incident Commander     | UNKNOWN       | select provider and approve network/TLS plan             |
| secrets               | Security            | Operations/SRE     | Security                     | Security Incident Lead | DESIGNED      | select manager and approve access/rotation               |
| monitoring/alerts     | Operations/SRE      | Primary On-Call    | Operations                   | Incident Commander     | DESIGNED      | select providers, routes, and actual assignees           |
| rate limits           | Engineering         | Operations/SRE     | Security and Product         | Incident Commander     | PROPOSED      | approve values and fail behavior                         |
| backup/PITR           | Data/DBA            | Operations/SRE     | Operations and Business      | Data Integrity Lead    | DESIGNED      | approve provider, RPO/RTO, and restore cadence           |
| retention/deletion    | Privacy             | Operations/SRE     | Privacy and Business         | Privacy Lead           | DESIGNED      | approve values, workflow, and backup handling            |
| artifact/provenance   | Engineering         | Release Manager    | Security and Release Manager | Incident Commander     | DESIGNED      | select registry/CI and approve immutable promotion       |
| support/status        | Support             | Communications     | Support and Release Manager  | Incident Commander     | UNKNOWN       | select channels and approve playbook                     |
| launch window         | Release Manager     | Incident Commander | Business/Executive           | Business/Executive     | PENDING       | approve staffed window and rollback deadline             |

Role labels are accountability placeholders, not actual assignments. All rows
remain launch-blocking until a named team/person and approval source exist.

## Prompt 20-D-R3 Approved Pilot Decisions

- Production decision owner, operational owner, deployment authority, manual
  disk-recovery authority, and conditional pilot-opening authority: Mustafa
  Bedir.
- Target: Hetzner Cloud CX33 in `nbg1`; account and VPS are pending
  provisioning.
- Runtime: Ubuntu Server 24.04 LTS with Docker on one VPS.
- PostgreSQL and Redis: self-managed containers on that VPS; Redis is not the
  durable system of record.
- Edge: DuckDNS, Caddy, and Let’s Encrypt; all external records/certificates are
  pending provisioning.
- Secret storage: root-only production `.env`; actual values remain absent and
  must never enter Git or logs.
- Monitoring/alerts: Uptime Kuma, host/container metrics, and a Telegram alert
  path; services and identifiers are pending provisioning.
- Registry/CI: private GHCR package and GitHub Actions; credentials, workflow,
  and production image publication remain pending.

Configuration-owner and independent escalation assignments not explicitly
approved in the package remain unassigned. This section records decisions, not
resource existence or deployment authorization.
