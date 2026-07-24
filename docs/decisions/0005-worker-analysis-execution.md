# 0005: Authoritative worker full-game execution

## Context

Prompt 9 owns queue delivery, worker claims, leases, retries, and terminal job transitions.
Prompts 10-B and 10-C provide bounded full-game orchestration and complete-only persistence,
but neither was connected to the worker.

## Decision

The analysis task claims and starts one generation, reloads the current `RUNNING` job and its
server-owned completed game, and builds the orchestration input only from database fields. The
configured game-time budget must be shorter than the lease. One `StockfishEngine` adapter owns
one subprocess for the N+1 sequential position evaluations.

Only a complete result reaches finalization. The result rows and the exact owner/generation
`RUNNING -> SUCCEEDED` transition execute under one transaction and job-row lock. A lost owner,
generation change, completion rejection, or commit failure rolls back both sides. Engine and
budget failures use the existing sanitized retryable/terminal failure lifecycle; partial output
is never passed to persistence.

## Consequences

The worker now produces durable internal analysis records. It still does not publish engine
output, set `analysis_available_at`, change queue payloads, add endpoints, or expose a response
schema. Raw FEN remains transient orchestration input and is excluded from Prompt 10-C durable
analysis records and logs.

## Distributed runtime closure

Prompt 10-D-2 exercises this unchanged wiring with PostgreSQL 17, a Redis broker, real
Celery worker processes, and native Stockfish. A retryable engine-start failure schedules a
durable retry; an old broker delivery cannot claim the retry-scheduled job; the replacement
generation completes with Stockfish; and delivery of the same payload after the transactional
commit converges on the same single run. Invalid server-owned game data reaches the existing
terminal failure path without durable engine output. Killing a worker while its Stockfish
subprocess is observed leaves the job recoverable after lease expiry, and a new worker/generation
is the only authority permitted to persist and complete. The suite repeats from a fresh database
and creates and removes isolated Redis, worker, and engine resources per scenario.
