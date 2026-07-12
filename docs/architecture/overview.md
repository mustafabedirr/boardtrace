# Architecture Overview

## Components

- **Capture client**: the extension processes only a user-selected board region, detects position changes, and submits scoped capture data.
- **FastAPI backend**: validates requests, owns server-side game state, persists commands, schedules work, and enforces report locks.
- **Vision worker**: converts approved board captures into validated position and FEN candidates.
- **Engine worker**: runs native Stockfish with python-chess UCI. This is the only Stockfish execution location.
- **Report worker**: creates post-game evaluations, classifications, comparisons, variations, and summaries after release conditions are met.
- **PostgreSQL**: authoritative game state, transitions, analysis metadata, and locked report data.
- **Redis**: background-job coordination and caching.
- **Object storage**: retention-controlled approved capture artifacts, compatible with MinIO or S3.
- **Next.js analysis application**: displays only backend-released post-game reports.

## Data flow

1. The user selects a board region in the capture client.
2. The capture client submits changed, scoped capture data to FastAPI.
3. FastAPI records lifecycle state in PostgreSQL, stores approved artifacts, and schedules vision work through Redis.
4. Vision produces validated position candidates; engine work produces locked server-side analysis.
5. After game completion is verified, report work creates the post-game review.
6. Only at `ANALYSIS_AVAILABLE` may the Next.js application retrieve the report.

## Live-game confidentiality

During an active game, client-facing HTTP responses, WebSocket messages, browser state, local storage, and IndexedDB must contain no `bestMove`, `evaluation`, `principalVariation`, `mateScore`, alternative moves, or equivalent engine-derived data. The client receives only capture-lifecycle status.

## Modular-monolith boundaries

Capture, games, vision, analysis, reporting, storage, and audit are explicit internal modules with deliberate interfaces and durable state. They share one backend codebase and coordinated deployment initially; queues and workers do not make them microservices. Extraction is deferred until real operational, ownership, reliability, or scaling evidence exists.
