# 0007: Classification-free move analytical metrics

## Context

Prompt 10-E provides an authorized, current-generation, immutable internal analysis snapshot.
Move-level analytical consumers need deterministic score deltas without introducing quality
labels, accuracy policy, aggregates, persistence, or public exposure.

## Decision

The pure derivation service accepts only the Prompt 10-E internal snapshot contract. For every
move, the before evaluation is already from the mover's side-to-move perspective. The after
evaluation is from the opponent's side-to-move perspective and is negated to normalize it to the
mover. Position references and the side-to-move change are validated before derivation.

For centipawn-to-centipawn transitions:

```text
centipawn_delta = after_cp_from_mover - before_cp_from_mover
raw_centipawn_loss = before_cp_from_mover - after_cp_from_mover
raw_centipawn_loss = -centipawn_delta
centipawn_loss = max(0, raw_centipawn_loss)
```

`centipawn_delta` is the signed evaluation change: positive means the mover's normalized
evaluation improved and negative means it worsened. `raw_centipawn_loss` is its additive inverse:
positive means deterioration and negative means improvement/noise. The raw loss remains available
as typed diagnostic data, while the public-internal loss value is clamped to zero and the clamp is
explicitly marked. No tolerance or quality threshold is introduced.

Mate-to-mate, centipawn-to-mate, mate-to-centipawn, and missing-score transitions are separate
typed outcomes and never receive a synthetic centipawn delta or loss. Mate distance signs are
normalized using the same mover-perspective rule. Terminal-after-position is explicit metadata
and does not invent a different score conversion.

## Consequences

The output is an immutable internal per-move contract tied to the authoritative run ID and lease
generation. It contains no move label, classification threshold, accuracy value, ACPL aggregate,
player/game summary, explanation, or release decision. The service performs no database writes,
engine calls, replay, caching, worker changes, API registration, response serialization, or
OpenAPI exposure.
