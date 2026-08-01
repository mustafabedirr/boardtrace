# BoardTrace Production Backup and PITR Governance

| Control         | Provider/system | Policy                                                 | Owner                       | Approval | Activation stage | Decision   |
| --------------- | --------------- | ------------------------------------------------------ | --------------------------- | -------- | ---------------- | ---------- |
| database backup | UNKNOWN         | encrypted automated backups required                   | Data/Operations             | PENDING  | NOT PROVISIONED  | INCOMPLETE |
| PITR            | UNKNOWN         | decision required                                      | Data/Operations             | PENDING  | NOT PROVISIONED  | INCOMPLETE |
| backup storage  | UNKNOWN         | separate protected storage and access required         | Security/Operations         | PENDING  | NOT PROVISIONED  | INCOMPLETE |
| restore testing | UNKNOWN         | scheduled restore plus integrity verification required | Data/Operations             | PENDING  | NOT TESTED       | INCOMPLETE |
| RPO             | n/a             | numeric target required                                | Product/Business/Operations | PENDING  | NOT APPROVED     | MISSING    |
| RTO             | n/a             | numeric target required                                | Product/Business/Operations | PENDING  | NOT APPROVED     | MISSING    |

The repository runbook defines a safe workflow but does not select a provider
or approve policy values. Backup execution, PITR enablement, restore execution,
credential creation, and production mutation are zero.

## Prompt 20-D-R3 Approved Pilot Recovery Policy

- daily full logical PostgreSQL backup;
- encrypt on the VPS with `age`, then upload only encrypted data to Cloudflare
  R2 bucket alias `boardtrace-pilot-backups`;
- retain off-site backups for 30 days;
- keep no private age key on the VPS or in cloud storage;
- verify object existence, file size, and checksum before deleting the local
  copy;
- retain local copy when verification fails;
- RPO: approximately 24 hours;
- RTO: 4 hours;
- restore test: monthly in a separate test environment.

This is a backup/rebuild policy, but the package does not explicitly decide
whether database PITR is disabled, unavailable, or required later. D20R2-015
therefore remains missing despite approved backup/RPO/RTO/restore values. R2
resources, credentials, and age keys are pending provisioning, and no
production backup or restore test has run.
