# ADR 0012: Authorized Post-Game Analysis Public Boundary

- Status: Accepted
- Date: 2026-07-24

## Decision

BoardTrace exposes one authenticated, single-shot JSON read:

```text
GET /api/v1/analysis/games/{game_id}
```

The delivery service first requires an owner match, verified game completion,
and the exact `ANALYSIS_AVAILABLE` release state. Only then does it invoke the
canonical `InternalAnalysisReadFacade`, which selects the current authoritative
generation and builds the unified internal aggregate. Missing, foreign, live,
finished-but-unreleased, and analysis-running games all fail closed without
returning analysis.

The public DTO module imports no persistence, engine, internal analysis, or
service contracts. Mapping is explicit and allowlisted. Public fields are:

- game ID;
- played move ply, UCI, SAN, mover, quality, and clamped CPL when eligible;
- white/black move counts, CPL coverage, ACPL, accuracy, classification
  coverage, and quality counts.

Run/job IDs, owner ID, lease generation, analysis version, position IDs,
engine/configuration details, raw scores, mate scores, best moves, principal
variations, reference moves, signed deltas, raw loss, and internal
classification reasons are excluded.

The endpoint accepts regular authenticated user tokens only; extension tokens,
anonymous access, and cross-owner access are rejected. Responses use
`Cache-Control: no-store` and `Pragma: no-cache`.

## Consequences

- Public analysis remains locked until server-owned post-game release.
- OpenAPI contains only the explicit public DTO graph.
- Reads perform no writes and do not invoke Stockfish, workers, queues, or
  persistence mutation paths.
- No polling, streaming, UI, sharing, re-analysis, or historical selector is
  introduced.
- Live-game engine output remains forbidden.
