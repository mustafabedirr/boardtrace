# 0002: Backend-only Stockfish engine foundation

## Context

BoardTrace needs a native chess engine only after server-side game completion has been
verified. Sending an engine executable, engine input, or engine output to a client would
break the live-analysis lock.

## Decision

The API package depends on `python-chess` only for its UCI protocol adapter. A typed,
internal `StockfishEngine` launches the configured native executable only when a worker
calls it with server-derived, post-game authorization. Importing the module and creating
the FastAPI application do not launch a process. Its result types are internal domain
objects; no endpoint, response schema, persistence path, or worker task is added here.

Each bounded adapter session owns a fresh native process. A standalone position call is
a one-call session; full-game orchestration may send its N+1 sequential position calls
through one session. `popen_uci` must complete the UCI startup handshake before the
process is considered ready, and the configured command timeout bounds startup and
protocol operations. Sessions sharing an adapter instance are serialized. Timeout,
crash, engine error, and caller cancellation all invalidate and clean up that session's
process; a later session starts a new process rather than reusing uncertain protocol
state.

`python-chess` is maintained, has no service cost, and supplies the approved UCI boundary
without implementing a custom subprocess protocol. The standard library alone is not a
safe replacement because correct UCI lifecycle, parsing, and shutdown handling would be
application-owned.

## Consequences

The domain contract has two distinct gates. Job creation accepts only a server-verified
`FINISHED` game. Engine execution accepts a server-verified `FINISHED` game and also
`DEEP_ANALYSIS_RUNNING`, the state occupied while authorized engine work is executing.
`ANALYSIS_AVAILABLE` is the client release state, not permission to start more engine
work. Active, unverified, failed, released, and mismatched requests fail before a native
process is started. A later worker integration must preserve these gates and must not
expose the internal result types before the server releases analysis.
