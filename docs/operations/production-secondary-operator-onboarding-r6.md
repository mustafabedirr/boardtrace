# BoardTrace R6 Secondary-Operator Onboarding

Status: `READY_FOR_PROVISIONING / BLOCKED`. Mode A created no account.

## Identity and activation

- Person: Ahmet Bedir
- Linux account: `ahmet`
- Separate SSH public key required; no credential sharing
- Activation: Mustafa Bedir cannot be reached

## Authorized scope

The root-owned dispatcher permits only `status`, `stop`, `restart`, `rollback`
to the previous-known-good image, and `health`. The sudoers entry must reference
only `/usr/local/sbin/boardtrace-recovery`; `NOPASSWD: ALL` is prohibited.

Ahmet must be unable to deploy a new release, build/push/login to a registry,
edit SSH/firewall/architecture, read `/opt/boardtrace/.env`, retrieve secrets,
open a root shell, change policy, accept risk, expand the pilot, or approve a
launch.

## Mode B onboarding and revocation checks

- [ ] distinct account/key and fingerprint recorded
- [ ] `visudo -cf` passes; `sudo -l -U ahmet` shows only the dispatcher
- [ ] every permitted dispatcher action works with synthetic/empty state
- [ ] prohibited command, root-shell, secret-read and config-edit attempts fail
- [ ] command audit evidence is enabled and contains no secrets
- [ ] revocation rehearsal locks the account/removes key and is then restored
- [ ] first staffed recovery drill passes with critical defects resolved

Revocation: lock `ahmet`, remove only Ahmet's `authorized_keys` entry and scoped
sudoers file, verify login denial, preserve the primary administrator account.
