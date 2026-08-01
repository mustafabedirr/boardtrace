# BoardTrace R6-R1 MODE B Authorization Packet

This packet is a request boundary, not authorization. Source of truth:
`infrastructure/production/external-mutation-plan.r6.json`. Commit authorization,
MODE B authorization, deployment authorization, and launch authorization are
separate decisions.

| Seq | System / exact action | Resource | Cost | Reversible / rollback | Main risk | Credential category | Verification | Exposure / participants |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Select/create project; register one approved public key | Hetzner `BoardTrace Pilot` | No server charge asserted | Yes; remove key/delete empty project | wrong project or key | Hetzner token; public key | `hcloud context active`; `hcloud ssh-key list` | no public change; Mustafa |
| 2 | Create exactly one CX33 and bounded firewall | `boardtrace-pilot-01`, `nbg1` | recurring server/IPv4; quote required | Yes; remove protection/server/firewall | charge, wrong region, unsafe firewall | Hetzner token | server/firewall describe | creates public host; Mustafa |
| 3 | Install host packages/Docker and restrictive paths | Ubuntu host | bandwidth/operator time | Rebuild if unsafe | daemon exposure or permission error | primary SSH key | OS/Docker/time/listener checks | no app exposure; Mustafa |
| 4 | Apply two-session SSH/UFW/Fail2ban hardening | Ubuntu host | none | versioned rollback from preserved session | administrator lockout | primary session; both public keys | `sshd -t/-T`, UFW, Fail2ban, listeners | changes SSH exposure; Mustafa + second-key verification |
| 5 | Create/update DNS record | `boardtrace.duckdns.org` | provider terms; no price asserted | restore/clear prior value | wrong-IP publication | DuckDNS token | `Resolve-DnsName` | public DNS change; Mustafa |
| 6 | Obtain one TLS certificate in maintenance mode | Caddy / Let's Encrypt | none expected | stop Caddy; remove 80/443 rules | unintended API/admin exposure | completed DNS control | Caddy validate; TLS handshake | maintenance response only; Mustafa |
| 7 | Create R2 bucket/lifecycle/least-privilege credential | `boardtrace-pilot-backups` | recurring storage/requests; quote required | revoke/delete test objects/empty bucket | excess privilege or retention error | Cloudflare authorization | lifecycle query | no application exposure; Mustafa |
| 8 | Run ciphertext-only synthetic backup/restore probe | `r6-synthetic-probe` | small temporary storage/requests | delete object/workdir | plaintext/key leakage | bucket credential; age recipient; off-host key | size/SHA-256/isolated restore | no public change; Mustafa |
| 9 | Authenticate and pull immutable image without starting it | approved GHCR version/digest | plan storage/bandwidth | logout/remove image | token leak or mutable tag | packages:read credential | image digest/architecture | no app exposure; Mustafa |
| 10 | Create/confirm bot/group and send labelled test | Telegram bot/group | none expected | remove bot/revoke token | sensitive alert payload | Telegram account/token | status-only alert probe | group-visible test; Mustafa |
| 11 | Create separate limited operator account/key | Linux account `ahmet` | none | lock account/remove key/sudoers | privilege escalation or secret access | Ahmet public key; admin session | `visudo -cf`; `sudo -l -U ahmet`; deny tests | SSH participation; Mustafa + Ahmet |
| 12 | Assemble root-only environment; run real preflight and staffed drill | `/opt/boardtrace/.env`; drill record | operator time/host resources | revoke secrets; controlled non-public state | secret exposure or incomplete recovery | all root-only contract secrets; both operators | preflight; file mode; drill evidence | traffic remains disabled; Mustafa + Ahmet |

## Authorization syntax

Only an explicit scope below is actionable:

- `AUTHORIZE_COMMIT_ONLY`
- `AUTHORIZE_MODE_B_PLAN_STEP_<N>`
- `AUTHORIZE_MODE_B_ALL_LISTED_STEPS`
- `DO_NOT_AUTHORIZE`

`AUTHORIZE_COMMIT_ONLY` creates no external resource. MODE B authorization does
not authorize production application deployment, public application traffic,
pilot users, technical go, or launch.
