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

`python-chess` is maintained, has no service cost, and supplies the approved UCI boundary
without implementing a custom subprocess protocol. The standard library alone is not a
safe replacement because correct UCI lifecycle, parsing, and shutdown handling would be
application-owned.

## Consequences

Only `FINISHED` or `DEEP_ANALYSIS_RUNNING` games with `completion_verified_at` may reach
the adapter. Active, unverified, failed, and mismatched game requests fail before a native
process is started. A later worker integration must preserve this gate and must not expose
the internal result types before the server releases analysis.
