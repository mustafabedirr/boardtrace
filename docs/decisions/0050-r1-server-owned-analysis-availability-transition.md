# ADR 0050-R1: Server-owned analysis availability transition

## Context

The Prompt 20-A controlled-staging exercise proved that an authoritative analysis
job could finish and persist a complete result while the owning game remained
before `ANALYSIS_AVAILABLE`. Public delivery correctly failed closed, but there
was no deployable server-owned release operation. Manual SQL, a client flag, and
new publication endpoints were rejected because they would bypass worker,
transaction, authorization, and audit authority.

## Existing lifecycle model

`Game.status` already uses `GameStatus`. The relevant existing states are
`FINISHED`, `DEEP_ANALYSIS_RUNNING`, and `ANALYSIS_AVAILABLE`; no schema or enum
change is required.

`ANALYSIS_AVAILABLE` means that the game is completion-verified, retains its
authoritative normalized moves and ingestion payload hash, and has a successful
current analysis job whose exact lease generation owns a complete current run
with all required position and move records.

## Decision

`AnalysisResultPersistenceService.persist_and_complete_owned_generation` is the
single transition owner. It is called only from the backend worker and accepts no
request or client publication input.

Within the existing `TransactionBoundary`, it:

1. locks and validates the exact running job and game;
2. validates worker identity, unexpired lease, lease generation, game identity,
   completion authority, and allowed predecessor state;
3. persists and flushes the complete deterministic analysis generation;
4. completes the exact owned job;
5. revalidates that the job is the current authoritative job, the run is complete
   and generation-matched, persisted row counts equal run metadata, all moves are
   complete, and the game retains authoritative ingestion facts;
6. sets `Game.status` to `ANALYSIS_AVAILABLE` and records
   `analysis_available_at`;
7. commits all result, job, and lifecycle mutations together.

Any error rolls back all three effects. Public reads continue to require the
existing backend lifecycle predicate and current complete run projection.

## Idempotency and concurrency

The deterministic run identity is derived from job ID and lease generation.
Repeated finalization of the already-available exact successful generation
returns that generation without rewriting result rows or changing the original
availability timestamp.

Wrong worker, wrong generation, expired lease, partial result, ineligible game,
foreign game/result identity, and a superseded job are rejected. Job and game row
locks plus the current-job check ensure that only the authoritative winner can
publish availability. Duplicate worker tasks remain no-ops at the claim gate.

## Audit contract

After the transaction commits, the service emits the bounded
`analysis_availability_transitioned` audit event with only job identity and the
stable `transitioned` or `idempotent` outcome. Audit adapter failures are caught
outside the business transaction. No move data, engine result, credential,
token, database topology, or private payload is logged. No high-cardinality
metric label was added.

## Public delivery and privacy

Before the transition, public result delivery remains unavailable. After commit,
the authenticated owner may receive only the existing public DTO. Non-owners and
unauthenticated callers remain denied. No public DTO field, endpoint, admin
publication route, arbitrary state setter, or client-controlled transition was
added.

## Evidence

Focused PostgreSQL tests cover:

- atomic persistence, job completion, lifecycle transition, and rollback;
- exact-generation idempotency and duplicate-row prevention;
- expired-lease, ineligible-game, and superseded-job denial;
- worker-to-owner public delivery and cross-user denial;
- post-commit audit timing and observer-failure isolation;
- real Stockfish worker persistence and availability.

Broader concurrency, public-read, readiness, and aggregate suites preserve the
existing current-run and privacy contracts. Canonical regression counts are
reported in the Prompt 20-A-R1 completion record.

## Consequences

Prompt 20-A's original source blocker is resolved. Prompt 20-A is not accepted by
this ADR and remains blocked pending a fresh controlled-staging rerun. ADR 0050
remains reserved for successful Prompt 20-A acceptance. Prompt 20-B and
production deployment remain out of scope.
