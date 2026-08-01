# BoardTrace Production Capacity and Sizing

## Forecast

No authoritative initial users, DAU, peak concurrency, games/user, jobs/hour,
average move count, peak ingestion, or drain target was supplied. Forecast
approval is `INCOMPLETE`.

## Assumptions

| Metric             | Baseline                | Expected | Contingency | Source                    | Owner          | Confidence   | Review date | Decision   |
| ------------------ | ----------------------- | -------- | ----------- | ------------------------- | -------------- | ------------ | ----------- | ---------- |
| requests           | 2,041 over 66m52.9s     | UNKNOWN  | UNKNOWN     | Prompt 20-B staging       | Product Owner  | staging-only | PENDING     | INCOMPLETE |
| completed analyses | 67                      | UNKNOWN  | UNKNOWN     | Prompt 20-B staging       | Product Owner  | staging-only | PENDING     | INCOMPLETE |
| maximum queue      | 7; drained in 3.0s      | UNKNOWN  | UNKNOWN     | Prompt 20-B staging       | Operations/SRE | staging-only | PENDING     | INCOMPLETE |
| peak concurrency   | not a business forecast | UNKNOWN  | UNKNOWN     | no authoritative forecast | Product Owner  | none         | PENDING     | INCOMPLETE |

## Staging Evidence

Maximum observed connections: 5; Redis memory: 1,488,672 bytes; API memory:
4,403,200 bytes; worker memory: 4,407,296 bytes; web memory: 9,506,816 bytes;
Stockfish children: 1. These values are observations, not production sizing
certification.

## Model and Initial Sizing

| Component        | Proposed size                                      | Forecast input | Staging evidence            | Headroom | Scaling trigger                       | Owner                  | Approval | Decision   |
| ---------------- | -------------------------------------------------- | -------------- | --------------------------- | -------- | ------------------------------------- | ---------------------- | -------- | ---------- |
| API              | NOT SET                                            | missing        | observed only               | NOT SET  | NOT SET                               | Engineering/Operations | PENDING  | INCOMPLETE |
| web              | NOT SET                                            | missing        | observed only               | NOT SET  | NOT SET                               | Engineering/Operations | PENDING  | INCOMPLETE |
| worker/Stockfish | one process is the observed serialization boundary | missing        | 67 completions; queue max 7 | NOT SET  | queue age/backlog threshold NOT SET   | Engineering/Operations | PENDING  | INCOMPLETE |
| PostgreSQL       | NOT SET                                            | missing        | maximum 5 connections       | NOT SET  | connections/latency threshold NOT SET | Data/Operations        | PENDING  | INCOMPLETE |
| Redis            | NOT SET                                            | missing        | maximum 1,488,672 bytes     | NOT SET  | memory/queue threshold NOT SET        | Engineering/Operations | PENDING  | INCOMPLETE |

## Headroom, Scaling, and Review

No numeric headroom, scaling trigger, or review schedule is approved. Product
must supply the forecast; Operations must model scenarios; Engineering,
Operations, Product, and Business/Executive must approve the result.

## Claim Boundary

Production capacity certification is explicitly **not claimed**.

## Prompt 20-D-R3 Approved Closed-Pilot Envelope

| Metric                     | Approved pilot decision                                                |
| -------------------------- | ---------------------------------------------------------------------- |
| invited users              | 5                                                                      |
| expected concurrent users  | 1-2                                                                    |
| volume                     | about 2 games/user/day; about 10 analyses/day                          |
| expected peak              | 2 analyses/hour                                                        |
| VPS                        | Hetzner Cloud CX33, single VPS, no HA                                  |
| global concurrent analyses | 2                                                                      |
| active analyses per user   | 1                                                                      |
| maximum queued jobs        | 3, FIFO                                                                |
| analysis deadline          | 3 minutes; failure on timeout; no automatic retry                      |
| expansion gate             | 2 stable weeks, zero critical incidents, at least 95% within 3 minutes |
| expansion stop             | failure or over-3-minute rate above 5%                                 |

These are authoritative human decisions. External capacity is not provisioned
or certified, and the queue/concurrency behavior has not been verified against
the production source. D20R2-010 and D20R2-011 are resolved; D20R2-012 remains
missing because the package does not provide the complete login, pairing,
ingestion, scheduling, polling/delivery rate-limit contract required by R2.
