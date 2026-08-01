# BoardTrace R6 Production Preflight Evidence

Mode A result: `BLOCKED AS DESIGNED — REAL VALUES ABSENT`.

| Category                              | Mode A result                               |
| ------------------------------------- | ------------------------------------------- |
| decision package                      | PASS                                        |
| R5-R2 evidence qualification          | PASS — 10 temp and 5 PostgreSQL tests rerun |
| provisioning manifest/mutation plan   | PASS — zero mutations                       |
| SSH/sudoers repository artifacts      | PASS; real host PENDING                     |
| Hetzner host identity/Ubuntu/Docker   | PENDING MODE B                              |
| firewall/Fail2ban/listeners           | PENDING MODE B                              |
| DuckDNS/TLS                           | PENDING MODE B                              |
| R2/lifecycle/encrypted external probe | PENDING MODE B                              |
| immutable GHCR image/digest           | PENDING MODE B                              |
| Telegram controlled alert             | PENDING MODE B                              |
| root-only production environment      | PENDING MODE B                              |
| no-bypass real-value environment gate | EXPECTED FAIL IN MODE A                     |
| secondary account/permissions/drill   | PENDING MODE B                              |
| metadata-only logging                 | PASS repository policy/runtime              |

The real preflight may pass only after every external value exists and every
host/provider check is performed. It must emit categories and missing names,
never secret values, and cannot deploy or enable public application traffic.
