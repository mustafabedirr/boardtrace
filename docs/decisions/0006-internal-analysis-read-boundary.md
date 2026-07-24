# 0006: Internal authorized analysis snapshot reads

## Context

Prompt 10-C persists complete, generation-aware analysis snapshots. Those records need an
application read foundation without creating a public API or weakening the live-game boundary.

## Decision

An internal read service accepts a server-owned game ID and requesting user ID. It queries the
game ownership and lifecycle first. Missing games, ownership mismatch, and unavailable lifecycle
states are distinguished before any analysis table is queried. Live or unverified games fail
closed.

After authorization, the repository selects the highest current analysis version. It never
falls back to an older complete run when the current job is nonterminal. A successful current
job must have one complete run matching its exact job ID, game ID, analysis version, and lease
generation. Missing or mismatched durable state is corrupt rather than unavailable.

Ordered position and move rows are reconstructed into frozen internal records. Snapshot schema,
counts, contiguous ply ordering, move references, score representation, UCI encodings, bounded
numeric values, and engine configuration are validated during read-back. Validation errors expose
no engine payload and fail closed as corrupt state.

## Consequences

The composition function is application-internal and is not registered as a FastAPI dependency.
No route, response schema, OpenAPI component, SSE/WebSocket message, UI state, extension field,
cache, persistence write, worker behavior, or Stockfish acquisition is added. Internal reads do
not imply that a snapshot is released to a client; public release remains a later explicit phase.
