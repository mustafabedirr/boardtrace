"""Pure internal move-level analytical metric derivation."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import chess

from boardtrace_api.analysis.stockfish import StockfishScore
from boardtrace_api.services.analysis_reads import InternalAnalysisSnapshot


class MoveMetricDerivationError(ValueError):
    """Raised when an internal snapshot cannot support deterministic derivation."""


class NormalizedScoreKind(StrEnum):
    CENTIPAWN = "CENTIPAWN"
    MATE = "MATE"
    MISSING = "MISSING"


class MoveMetricOutcome(StrEnum):
    CENTIPAWN_LOSS = "CENTIPAWN_LOSS"
    MATE_TO_MATE = "MATE_TO_MATE"
    CENTIPAWN_TO_MATE = "CENTIPAWN_TO_MATE"
    MATE_TO_CENTIPAWN = "MATE_TO_CENTIPAWN"
    MISSING_SCORE = "MISSING_SCORE"


@dataclass(frozen=True)
class NormalizedMoveScore:
    kind: NormalizedScoreKind
    centipawns: int | None = None
    mate_in: int | None = None

    def __post_init__(self) -> None:
        if self.kind is NormalizedScoreKind.CENTIPAWN:
            valid = self.centipawns is not None and self.mate_in is None
        elif self.kind is NormalizedScoreKind.MATE:
            valid = self.centipawns is None and self.mate_in is not None
        else:
            valid = self.centipawns is None and self.mate_in is None
        if not valid:
            raise ValueError("normalized score fields do not match score kind")


@dataclass(frozen=True)
class MoveMetricInput:
    ply: int
    move_uci: str
    move_san: str
    reference_best_move_uci: str | None
    mover: chess.Color
    before_side_to_move: chess.Color
    after_side_to_move: chess.Color
    before_score: StockfishScore | None
    after_score: StockfishScore | None
    after_is_terminal: bool


@dataclass(frozen=True)
class MoveAnalyticalMetric:
    ply: int
    move_uci: str
    move_san: str
    reference_best_move_uci: str | None
    mover: chess.Color
    before: NormalizedMoveScore
    after: NormalizedMoveScore
    outcome: MoveMetricOutcome
    centipawn_delta: int | None
    raw_centipawn_loss: int | None
    centipawn_loss: int | None
    negative_loss_clamped: bool
    after_is_terminal: bool


@dataclass(frozen=True)
class InternalMoveMetrics:
    game_id: UUID
    analysis_run_id: UUID
    lease_generation: int
    moves: tuple[MoveAnalyticalMetric, ...]


class MoveMetricDerivationService:
    """Derives metrics only from a 10-E authorized authoritative snapshot."""

    def derive(self, snapshot: InternalAnalysisSnapshot) -> InternalMoveMetrics:
        if snapshot.game_id != snapshot.analysis.result.game_id:
            raise MoveMetricDerivationError("snapshot game authority does not match result")
        metrics = tuple(
            derive_move_metric(
                MoveMetricInput(
                    ply=move.ply,
                    move_uci=move.move_uci,
                    move_san=move.move_san,
                    reference_best_move_uci=move.before.best_move_uci,
                    mover=move.before.side_to_move,
                    before_side_to_move=move.before.side_to_move,
                    after_side_to_move=move.after.side_to_move,
                    before_score=move.before.score,
                    after_score=move.after.score,
                    after_is_terminal=move.after.best_move_uci == "0000",
                )
            )
            for move in snapshot.analysis.result.move_evaluations
        )
        return InternalMoveMetrics(
            game_id=snapshot.game_id,
            analysis_run_id=snapshot.analysis.run_id,
            lease_generation=snapshot.analysis.lease_generation,
            moves=metrics,
        )


def derive_move_metric(value: MoveMetricInput) -> MoveAnalyticalMetric:
    if value.ply < 1:
        raise MoveMetricDerivationError("move ply must be positive")
    if value.before_side_to_move != value.mover:
        raise MoveMetricDerivationError("before position is not from mover turn")
    if value.after_side_to_move == value.mover:
        raise MoveMetricDerivationError("after position did not change side to move")

    before = _normalize(value.before_score, value.before_side_to_move, value.mover)
    after = _normalize(value.after_score, value.after_side_to_move, value.mover)
    outcome = _outcome(before.kind, after.kind)
    centipawn_delta: int | None = None
    raw_centipawn_loss: int | None = None
    centipawn_loss: int | None = None
    negative_loss_clamped = False
    if outcome is MoveMetricOutcome.CENTIPAWN_LOSS:
        if before.centipawns is None or after.centipawns is None:
            raise AssertionError("centipawn outcome is missing a centipawn score")
        centipawn_delta = after.centipawns - before.centipawns
        raw_centipawn_loss = -centipawn_delta
        negative_loss_clamped = raw_centipawn_loss < 0
        centipawn_loss = max(0, raw_centipawn_loss)

    return MoveAnalyticalMetric(
        ply=value.ply,
        move_uci=value.move_uci,
        move_san=value.move_san,
        reference_best_move_uci=value.reference_best_move_uci,
        mover=value.mover,
        before=before,
        after=after,
        outcome=outcome,
        centipawn_delta=centipawn_delta,
        raw_centipawn_loss=raw_centipawn_loss,
        centipawn_loss=centipawn_loss,
        negative_loss_clamped=negative_loss_clamped,
        after_is_terminal=value.after_is_terminal,
    )


def _normalize(
    score: StockfishScore | None,
    score_side: chess.Color,
    mover: chess.Color,
) -> NormalizedMoveScore:
    if score is None:
        return NormalizedMoveScore(NormalizedScoreKind.MISSING)
    multiplier = 1 if score_side == mover else -1
    if score.centipawns is not None:
        return NormalizedMoveScore(
            NormalizedScoreKind.CENTIPAWN,
            centipawns=score.centipawns * multiplier,
        )
    if score.mate_in is not None:
        return NormalizedMoveScore(
            NormalizedScoreKind.MATE,
            mate_in=score.mate_in * multiplier,
        )
    return NormalizedMoveScore(NormalizedScoreKind.MISSING)


def _outcome(before: NormalizedScoreKind, after: NormalizedScoreKind) -> MoveMetricOutcome:
    if NormalizedScoreKind.MISSING in {before, after}:
        return MoveMetricOutcome.MISSING_SCORE
    if before is NormalizedScoreKind.CENTIPAWN and after is NormalizedScoreKind.CENTIPAWN:
        return MoveMetricOutcome.CENTIPAWN_LOSS
    if before is NormalizedScoreKind.MATE and after is NormalizedScoreKind.MATE:
        return MoveMetricOutcome.MATE_TO_MATE
    if before is NormalizedScoreKind.CENTIPAWN:
        return MoveMetricOutcome.CENTIPAWN_TO_MATE
    return MoveMetricOutcome.MATE_TO_CENTIPAWN
