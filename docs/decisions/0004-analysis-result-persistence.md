# 0004: Generation-aware analysis result persistence

## Context

Prompt 10-B produces internal, immutable full-game position and move evaluation records.
They need an all-or-nothing PostgreSQL persistence boundary without connecting Stockfish
to Celery, completing jobs, or exposing engine output to a client.

## Decision

Three internal tables store an analysis run, its ordered position evaluations, and its
ordered move evaluations. A run is uniquely identified by analysis-job ID and positive
lease generation. UUIDv5 namespaces deterministically derive the run ID and every child
ID from that generation and ply.

The repository locks both the analysis-job row and game row. Writes require an exact
`RUNNING` job worker ID and lease generation, matching game ID, a server-verified
completion timestamp, and a `FINISHED` or `DEEP_ANALYSIS_RUNNING` game state. This check
prevents stale workers and live games from accepting engine output.

Writing the same generation replaces its child records under the same deterministic
identities. A later lease generation produces a distinct run and retains the earlier
generation. The service owns one explicit transaction for run metadata, every position,
and every move. Any validation, flush, pre-commit hook, or commit failure rolls back the
entire generation write.

The durable boundary is complete-only. A result must have `COMPLETE` status, no failure
metadata, all expected position evaluations, and all completed move evaluations before a
transaction may begin. Partial, cancelled, failed, timed-out, and budget-exhausted outputs
remain in memory and are never durable. Existing status and failure columns remain part of
the Prompt 10-C schema but this boundary never writes their non-complete variants.

The run stores allowlisted, bounded engine configuration fields in a versioned JSONB
snapshot. It also stores engine identity, record counts, and timestamps. It does not store
classifications, accuracy, centipawn-loss policy, explanations, or client release state.
Raw FEN is deliberately excluded from analysis position rows, the JSONB snapshot, durable
typed read-back records, and every persistence identity or comparison payload. This design
uses deterministic run/position UUIDs and relational keys rather than a FEN fingerprint.
The persistence path adds no FEN-bearing log or audit context.

## Consequences

Deleting a game cascades through jobs and runs to position and move evaluation records.
The persistence models are not response schemas and have no endpoint, SSE, WebSocket,
UI, extension, queue payload, or worker-execution integration. Persisted engine output
remains backend-internal and unavailable to clients in this phase.

Internal typed read-back reconstructs a complete immutable full-game result and bounded
configuration snapshot from ordered rows. It fails closed on non-complete run metadata,
missing position references, invalid snapshot fields, or count mismatches. This read path
is not a public release path.

The job row lock provides the serialization point for replacement and terminal-state
races. Identical concurrent writes converge on one generation and deterministic identities.
Different concurrent replacements apply in acquired lock order. If persistence owns the
lock first, it commits before job completion; if completion owns it first, the late write
observes terminal job state and is rejected. Stale owners and generations cannot overwrite
current authority.

This decision does not remove the pre-existing `games.initial_fen` and `positions.fen`
capture/game-domain fields. They are outside the Prompt 10-C analysis-result category and
remain necessary to represent server-authoritative custom starts and captured positions.
