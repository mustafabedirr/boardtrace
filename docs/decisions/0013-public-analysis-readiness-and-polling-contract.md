# ADR 0013: Public Analysis Readiness and Polling Contract

- Status: Accepted
- Date: 2026-07-24

## Decision

Authenticated normal game owners may query:

```text
GET /api/v1/analysis/games/{game_id}/status
```

The endpoint returns only `game_id`, an exact five-state readiness enum,
`result_available`, and bounded polling guidance. It is separate from the
Prompt 11-A result endpoint and never returns moves, classifications, CPL,
accuracy, engine output, or player aggregates.

The current job is selected by descending analysis version, creation time, and
ID. Public mapping is:

- no job: `NOT_STARTED`;
- pending, queued, or retry scheduled: `QUEUED`;
- claimed or running: `RUNNING`;
- failed or cancelled: `FAILED`;
- succeeded plus an exact current version/generation complete run and
  `ANALYSIS_AVAILABLE`: `READY`;
- every inconsistent combination fails closed as `FAILED`.

Historical successful runs are never used when a newer job exists. Job IDs,
run IDs, versions, lease generations, attempts, worker identity, timestamps,
failure details, and retry lifecycle state remain internal. The exact public
enum is `NOT_STARTED`, `QUEUED`, `RUNNING`, `READY`, and `FAILED`.

Clients may retry only `QUEUED` and `RUNNING`. Suggested delays remain 2
seconds for ordinary queued work, 3 seconds for running work, and 5 seconds
when the internally encapsulated job state is retry-scheduled. The contract
retains a 2-second minimum, 15-second maximum, and 1.5 backoff multiplier. The
endpoint also emits integer `Retry-After` seconds for those states. Terminal
states carry no retry delay.

Anonymous, extension-token, cross-owner, live, and unverified-game requests
fail closed. Responses use `no-store` and `no-cache`. The service is read-only
and performs no enqueue, worker, engine, re-analysis, persistence mutation,
cache, long polling, or streaming operation.
