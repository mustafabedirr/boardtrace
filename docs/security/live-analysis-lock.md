# Live Analysis Lock

## Threat model

The primary threat is a player receiving engine-derived guidance during an active game through API fields, WebSockets, client caches, extension storage, debug endpoints, premature report links, browser engines, or wrong finish detection.

## Why client-side hiding is insufficient

A hidden component does not protect data already sent to the browser: users can inspect network traffic, application state, local storage, IndexedDB, extensions, and source maps. Results must remain server-side until authorized release.

## Backend-only engine execution

Native Stockfish runs only in a backend engine worker via python-chess UCI. It never runs in a webpage, extension, Web Worker, or client runtime. Its output is locked server-side.

## Server-side game state

The backend is authoritative for lifecycle state and report eligibility. Client signals are evidence, not release authority. Transitions are validated and audit logged.

## Locked report endpoint

Report endpoints reject requests before `ANALYSIS_AVAILABLE` and must not leak `bestMove`, `evaluation`, `principalVariation`, `mateScore`, alternatives, or equivalent derived metadata.

## State machine

```text
CREATED
CAPTURING
FINISH_PENDING
FINISHED
DEEP_ANALYSIS_RUNNING
ANALYSIS_AVAILABLE
FAILED
```

Expected progression: `CREATED -> CAPTURING -> FINISH_PENDING -> FINISHED -> DEEP_ANALYSIS_RUNNING -> ANALYSIS_AVAILABLE`. `FAILED` is reachable on unrecoverable errors and retains audit context. Transition to `FINISHED` needs server-side verification.

## Audit logging

Log state transitions, lock checks, authorization decisions, job lifecycle events, and releases with timestamps and correlation IDs. Exclude secrets and sensitive capture data.

## Minimum data collection

Only the user-selected board region is processed. Full-screen images are not stored by default. Capture artifacts, user data, and logs follow minimization and retention principles.

## Game-end verification

The MVP combines lifecycle evidence, terminal-board or capture-inactivity signals where available, and a server-side confirmation window. Insufficient or conflicting evidence stays locked in `FINISH_PENDING` or fails safely.

## Known risks

Board recognition can be wrong; platform UI signals can change; compromised clients can submit misleading events; and operational defects can expose fields through new endpoints or logs.

## MVP controls

- Separate lifecycle and locked-analysis data.
- Use allowlisted, state-aware response serializers.
- Test that HTTP and WebSocket payloads omit engine fields before release.
- Deploy and check backend-only engine execution.
- Validate transitions server-side and audit them.
- Enforce scoped capture, retention controls, and no default full-screen persistence.
- Fail closed on uncertain game completion.
