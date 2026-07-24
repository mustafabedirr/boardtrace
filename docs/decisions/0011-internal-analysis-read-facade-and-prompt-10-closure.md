# ADR 0011: Internal Analysis Read Facade and Prompt 10 Closure

- Status: Accepted
- Date: 2026-07-24

## Decision

`compose_internal_analysis_read_facade` is the single application provider for
the complete internal Prompt 10 read chain. It resolves exactly one
`InternalAnalysisReadFacade` over one `InternalAnalysisAggregateService`. The
facade accepts only a game identifier and requesting user identifier, delegates
once, and returns the same immutable `UnifiedInternalAnalysisAggregate`.

The former intermediate read-service and aggregate-service provider functions
are removed. Their classes remain implementation details of the exact chain:

```text
internal facade
-> authorized current-generation snapshot
-> move metrics
-> classifications
-> white/black game aggregate
-> cross-layer identity validation
```

Authorization remains first and fails before job or result-table access.
Selection never falls back from a newer non-authoritative job to historical
results. When a newer complete run is authoritative, every derived layer must
carry that exact game, run, and lease-generation identity.

The facade is not registered with FastAPI and appears in no endpoint, public
schema, or OpenAPI component. It performs no writes and invokes no engine.
Production Stockfish construction remains confined to the backend worker.
Web and extension production sources contain no engine result contract; the
extension's only engine-field names are a rejection denylist.

## Prompt 10 completion audit

Prompt 10-A through 10-I evidence covers bounded native Stockfish lifecycle,
single-process full-game replay, complete-only transactional persistence,
generation/lease-safe worker completion, authorized current-generation reads,
deterministic metrics/classification/aggregation, and unified identity-closed
composition.

Subject to the repository quality, PostgreSQL integration, runtime, and
non-exposure gates remaining green, Prompt 10 backend is complete. No public
analysis delivery is authorized by this decision. The invariant remains:
no engine output during live games.

## Closure evidence

- Repository-wide API Ruff and strict Mypy gates pass.
- The complete API non-runtime suite passes against PostgreSQL 17.
- Facade integration tests prove authorization query short-circuiting, exact
  current-run selection, historical fallback prohibition, and cross-layer
  run/generation identity.
- OpenAPI and repository-owned web/extension source scans contain no internal
  read facade or analysis result contract.
- Extension lint, typecheck, and fair-play protocol tests pass. Its only engine
  field names form the explicit rejection denylist.
- Native Stockfish and distributed Redis/Celery/PostgreSQL recovery remain
  covered by the opt-in Prompt 10-A-2, 10-B-2, 10-C-2, 10-D, and 10-D-2 runtime
  suites; this facade does not change those execution paths.

Prompt 10-J and the Prompt 10 backend chain are complete. A pre-existing web
theme-toggle lint finding and the web package having no test files are outside
this backend-only change; no UI source is modified to conceal either result.
