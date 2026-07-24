# 0009: Internal player accuracy and game aggregates

## Context

Prompt 10-F provides immutable mover-normalized move metrics and Prompt 10-G provides immutable
internal classifications. Prompt 10-H needs deterministic white/black summaries without changing
classification, persisting aggregates, invoking the engine, or releasing results publicly.

## Decision

Moves are partitioned solely by their recorded mover color. Every move contributes to total move
count and exactly one quality-label count. Only centipawn-to-centipawn metrics with a validated
clamped loss are CPL-eligible. Mate transitions, missing scores, and all other non-CPL outcomes
remain visible in total, excluded, classification, and coverage counts but do not contribute to
summed loss, ACPL, or accuracy.

For each player:

```text
ACPL = summed_centipawn_loss / cpl_eligible_move_count
accuracy = 100 * 100 / (100 + ACPL)
```

Both values use `Decimal`, `ROUND_HALF_UP`, and two decimal places. Accuracy is bounded to
`[0.00, 100.00]`. When a player has no CPL-eligible moves, ACPL and accuracy are unavailable
(`None`) and `accuracy_available` is false; no synthetic zero is produced.

Classification coverage is the percentage of total moves whose quality is not `UNCLASSIFIED`.
It is rounded to two decimals. A player with no moves has unavailable coverage rather than a
synthetic percentage. Quality counts include every internal `MoveQuality` enum member in stable
enum order, including zero counts.

CPL coverage is a separate percentage:

```text
cpl_coverage = cpl_eligible_move_count / total_move_count * 100
```

It uses `Decimal`, `ROUND_HALF_UP`, and two decimal places. A zero-move player has `None` because
the denominator is zero. A player with moves but no CPL-eligible move has `0.00`. Mixed
eligible/excluded moves use the exact eligible-to-total ratio; excluded mate and missing-score
moves remain in the denominator.

## Consequences

The frozen game aggregate retains game ID, authoritative analysis run ID, lease generation, and
separate white/black summaries. Aggregation is pure, deterministic, and order-independent. It
does not create or alter move classification policy, persist accuracy/ACPL/classification, add a
table or migration, call Stockfish, modify workers, or register an API route, response schema,
OpenAPI component, stream, UI, extension field, leaderboard, or cross-game statistic.
