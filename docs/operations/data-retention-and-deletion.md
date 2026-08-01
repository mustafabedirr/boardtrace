# BoardTrace Data Retention and Deletion

No legal conclusion or organizational privacy approval is claimed.

| Data class                | Purpose                              | Retention                         | Deletion method                               | Backup implication                           | Owner               | Privacy approval | Decision   |
| ------------------------- | ------------------------------------ | --------------------------------- | --------------------------------------------- | -------------------------------------------- | ------------------- | ---------------- | ---------- |
| account/profile           | identity and account operation       | NOT APPROVED                      | authenticated service workflow required       | expiry/tombstone behavior not approved       | Identity/Product    | PENDING          | INCOMPLETE |
| game and normalized moves | post-game review                     | NOT APPROVED                      | owner-authorized service workflow required    | backup expiry not approved                   | Product/Data        | PENDING          | INCOMPLETE |
| board-scoped captures     | recognition evidence where necessary | NOT APPROVED; minimize by default | storage-object deletion plus metadata cleanup | backup expiry not approved                   | Privacy/Operations  | PENDING          | INCOMPLETE |
| analysis results          | authorized post-game analysis        | NOT APPROVED                      | owner-authorized service workflow required    | backup expiry not approved                   | Product/Data        | PENDING          | INCOMPLETE |
| audit/security metadata   | abuse and incident accountability    | NOT APPROVED                      | controlled expiry/deletion workflow required  | preservation/expiry rules not approved       | Security/Privacy    | PENDING          | INCOMPLETE |
| operational logs/metrics  | reliability and security operations  | NOT APPROVED                      | provider retention expiry required            | normally outside DB backup; provider unknown | Operations/Security | PENDING          | INCOMPLETE |

Deletion authority, identity verification, cascade/object cleanup, retry and
failure handling, audit evidence, legal-hold handling, backup expiry, and user
communication require Privacy, Security, Product, Operations, and
Business/Executive decisions. No deletion or retention control was activated.

## Historical Prompt 20-D-R3 pilot values (superseded in part)

- submitted game data: delete immediately after successful or failed analysis;
- analysis result/history: current session only; no analysis history;
- full PGN technical log: the former 24-hour allowance is `SUPERSEDED` by
  Prompt 20-D-R5-R2 and is not an active policy;
- logical database backups: 30-day off-site retention;
- local encrypted backup: delete only after verified Cloudflare R2 upload.

R5-R2 replaces the logging row with a metadata-only diagnostic contract. Full
PGN, FEN, raw move lists, game request bodies, and reconstructable engine I/O
are prohibited in all log categories. Safe operational metadata has a maximum
seven-day retention and Dozzle remains accessible only through an SSH tunnel;
it is not a game-content store. The supersession and runtime enforcement are
recorded in
`docs/production/decisions/boardtrace-production-logging-policy-supersession-r5-r2.md`
and `docs/operations/production-runtime-policy-alignment-r5-r2.md`.

This repository evidence does not constitute production provisioning,
deployment, legal advice, or launch authorization. External account/provider
retention controls still require provisioning-time verification.
