# 0008: Internal deterministic move classification policy

## Context

Prompt 10-F produces authoritative, mover-normalized move metrics with signed evaluation delta,
raw loss, clamped centipawn loss, and typed mate transitions. Prompt 10-G needs an explainable
internal quality label without adding accuracy, aggregates, persistence, engine work, or public
release.

## Decision

The immutable internal quality enum contains `BEST`, `EXCELLENT`, `GOOD`, `INACCURACY`,
`MISTAKE`, `BLUNDER`, and `UNCLASSIFIED`. The default centipawn-loss policy is:

| Clamped loss | Quality | Boundary |
| --- | --- | --- |
| 0–20 | `EXCELLENT` | both inclusive |
| 21–50 | `GOOD` | lower exclusive, upper inclusive |
| 51–100 | `INACCURACY` | lower exclusive, upper inclusive |
| 101–200 | `MISTAKE` | lower exclusive, upper inclusive |
| >200 | `BLUNDER` | lower exclusive |

Best-move equality compares the played UCI move with the before-position reference move after
both parse to canonical UCI. SAN and principal variation membership do not establish equality.

Conflict resolution is deterministic:

1. Decisive mate transitions are evaluated first, but beneficial transitions require exact
   reference equality to emit `BEST`.
2. Missing scores produce `UNCLASSIFIED`.
3. Exact best-move equality produces `BEST`.
4. Same-polarity mate states use their mate-aware fallback.
5. Centipawn-to-centipawn moves use the threshold table.
6. Indeterminate mate states produce `UNCLASSIFIED`.

Creating a forced win, escaping a forced loss, or flipping from forced loss to forced win is
`BEST` only when the played move exactly equals the before-position reference move; otherwise the
beneficial transition is `EXCELLENT`. Entering a forced loss, losing a forced win, or flipping
mate polarity from win to loss is `BLUNDER` regardless of reference equality. For same-polarity
mate preservation, an exact reference move is `BEST`; both forced-win preservation and remaining
forced loss are `GOOD` when the move is non-reference or the reference is missing. Mate-zero and
missing-score states remain unclassified.

## Consequences

Every classified record retains its source metric, reason, best-move equality result, run ID, and
lease generation. The classifier is pure and deterministic. It creates no brilliant/great/book/
only-move concepts, accuracy or ACPL values, aggregates, explanation text, persistence state,
database migration, worker behavior, Stockfish call, API route, response schema, or OpenAPI
surface.
