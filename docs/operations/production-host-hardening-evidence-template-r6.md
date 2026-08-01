# BoardTrace R6 Host-Hardening Evidence Template

Status: `UNEXECUTED — MODE A`. Complete only on the approved host in Mode B.
Do not record IP addresses unless operationally required and safely scoped; do
not record public keys, private keys, tokens, session cookies, or `.env` data.

| Check                                          | Safe evidence                                     | Result  |
| ---------------------------------------------- | ------------------------------------------------- | ------- |
| intended primary/secondary public keys present | fingerprints only                                 | PENDING |
| Ubuntu 24.04 / UTC / clock synchronized        | versions/status                                   | PENDING |
| SSH bootstrap syntax                           | `sshd -t` exit code                               | PENDING |
| bootstrap effective ports                      | key-only 22 and 48227                             | PENDING |
| second key session                             | established 48227 session, operator identity      | PENDING |
| final SSH syntax/effective policy              | 48227 only; no root/password/keyboard auth        | PENDING |
| password/root negative tests                   | exit/result categories only                       | PENDING |
| UFW                                            | public TCP 80, 443, 48227 only                    | PENDING |
| public port 22                                 | inaccessible after finalization                   | PENDING |
| private services                               | PostgreSQL/Redis/Dozzle/Kuma/Docker not public    | PENDING |
| Fail2ban/rate limiting                         | jail active on 48227                              | PENDING |
| rollback access                                | key-only two-port bootstrap restored in rehearsal | PENDING |

Required order: preserve the first session, install the bootstrap policy, open
a second key-authenticated session on 48227, create the root-owned `0600`
second-session marker from that session, then run
`finalize-host-hardening.sh` from the preserved session. If any check fails,
run the version-controlled rollback and keep R4-001 open.
