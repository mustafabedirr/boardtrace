# ADR 0010: Unified Internal Analysis Aggregate

- Status: Accepted
- Date: 2026-07-24

## Context

The authorized durable snapshot, move metrics, classifications, and player/game
summaries already exist as separate internal contracts. Callers need one
application-level read without weakening authorization or silently combining
records from different analysis generations.

## Decision

`InternalAnalysisAggregateService` performs exactly one Prompt 10-E authorized
read and passes that immutable snapshot through the existing Prompt 10-F,
Prompt 10-G, and Prompt 10-H pure services. It returns one frozen
`UnifiedInternalAnalysisAggregate`.

The composition validates the game identifier, analysis-run identifier, lease
generation, owner, durable move ordering, derived-to-classified move linkage,
player partition, and summary cardinalities across every layer. Any mismatch
fails closed with an internal composition error. Prompt 10-E not-found,
forbidden, unavailable, and corrupt-state errors retain their existing distinct
types.

The service is application-only. It is not a FastAPI dependency, response
schema, worker input, persistence model, or cache. Composition performs no
database writes and does not invoke Stockfish. All analysis data remains
unavailable to public API, browser, and extension contracts.

## Consequences

- A consumer receives one identity-closed internal analysis view.
- Authorization occurs before durable snapshot or derived-result access.
- No new analytical policy, persistence, endpoint, migration, or worker
  lifecycle is introduced.
- The invariant remains: no engine output during live games.
