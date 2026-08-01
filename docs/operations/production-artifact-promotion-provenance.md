# BoardTrace Production Artifact Promotion and Provenance

## Frozen Artifact Identity

| Artifact  | SHA-256                                                            |
| --------- | ------------------------------------------------------------------ |
| API wheel | `b12ef99a2b21e7bd6a1a748f7376acac92737ca14d349555e60274c8e83d2d62` |
| web       | `0f8278d80fe603782edab21d1fbc0f9c8a107f91c41ab4cdfc898dc7a3ce2613` |
| extension | `71c9c3249db8fdcddf908ddc1db98b47e91f9f16f777390acc2a0e81416493bb` |
| Stockfish | `9bde420202717ce083412027fbfb8c5c935b537591d712be8a8a8bae92f6e8d6` |

## Governance Status

| Control            | Required model                                                                         | Owner                       | Approval | Current status | Decision   |
| ------------------ | -------------------------------------------------------------------------------------- | --------------------------- | -------- | -------------- | ---------- |
| artifact registry  | selected registry with immutable digest addressing                                     | Release Manager/Engineering | PENDING  | UNKNOWN        | INCOMPLETE |
| build provenance   | source, build environment, dependency lock, builder, timestamp, and digest attestation | Engineering/Security        | PENDING  | DESIGNED       | INCOMPLETE |
| promotion policy   | promote accepted bytes by digest; never rebuild for production                         | Release Manager             | PENDING  | DESIGNED       | INCOMPLETE |
| rollback retention | retain accepted current and last-known-good immutable artifacts through stabilization  | Release Manager/Operations  | PENDING  | DESIGNED       | INCOMPLETE |
| CI/CD platform     | selected workflow with separated approval and deployment authority                     | Engineering/Security        | PENDING  | UNKNOWN        | INCOMPLETE |

No artifact was uploaded, promoted, signed, purchased, or deployed.

## Prompt 20-D-R3 Approved Pilot Decisions

- registry: private `ghcr.io/mustafabedirr/boardtrace`;
- CI: GitHub Actions performs build, tests, and image publication;
- API and worker may use one image with different commands;
- production deployment: manual, authorized to Mustafa Bedir;
- rollback: manually select the previous known-good versioned image;
- deployment must not rely only on `latest`.

GHCR credentials, workflow, immutable digest enforcement, build provenance,
signing/attestation decision, rollback-retention duration, and production image
publication are absent or pending. Therefore the provider decision is captured
under D20R2-009, while D20R2-017 remains a missing governance decision.
