# 0003: Backend full-game evaluation orchestration

## Context

BoardTrace needs deterministic position evaluations for every move of a completed game,
without exposing, persisting, classifying, or scoring those engine results in this phase.
The server-owned normalized move list and completion verification remain the only source
of authority.

## Decision

`FullGameAnalyzer` accepts an immutable completed-game input and bounded analysis budget.
It rejects unverified lifecycle states, empty games, invalid starting positions, illegal
moves, and games outside the move or position budget before invoking Stockfish. Replay
starts from standard chess initial position unless the server-owned game supplies an
initial FEN.

For N moves, the analyzer evaluates exactly N+1 unique positions. The evaluation after
one move is reused as the evaluation before the next move; no engine call is duplicated.
Scores retain the Prompt 10-A adapter contract and are relative to the side to move in
the recorded position. This phase does not derive centipawn loss, accuracy, or move
classification.

Each engine request receives both a depth limit and a time limit bounded by the smaller
of the per-position budget and remaining game deadline. Move and position count limits
bound total work. One full-game request opens one serialized adapter session, starts and
configures one Stockfish subprocess, evaluates all N+1 positions sequentially through
that process, and performs one cleanup when the session exits. UCI state is never shared
between separate full-game requests.

Records, checkpoints, failure details, and full-game results are typed and immutable.
An ordinary engine or deadline failure raises `FullGameAnalysisFailed`, carrying only
fully completed move records and a typed checkpoint. Caller cancellation is a control
signal, is not converted to a business failure, and continues through the Prompt 10-A
cleanup boundary.

The explicit reuse policy is `SINGLE_PROCESS_PER_GAME`. Startup, configuration, analysis,
deadline failure, partial failure, and caller cancellation all leave the session through
the same cleanup boundary. Standalone Prompt 10-A position calls remain one-call sessions.

## Consequences

The orchestration is an internal, synchronous, in-memory backend component. It is not
connected to SQLAlchemy models, repositories, migrations, Celery tasks, analysis-job
completion, API schemas, endpoints, SSE, WebSockets, UI, or browser code. A later phase
must explicitly design persistence and release authorization; it must not serialize
these internal records to clients before `ANALYSIS_AVAILABLE`.
