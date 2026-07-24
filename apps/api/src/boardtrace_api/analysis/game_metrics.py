"""Pure internal per-player and game analytical aggregation."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import chess

from boardtrace_api.analysis.move_classification import (
    ClassifiedMoveMetric,
    InternalClassifiedMoveMetrics,
    MoveQuality,
)
from boardtrace_api.analysis.move_metrics import MoveMetricOutcome

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal(100)


class GameMetricAggregationError(ValueError):
    """Raised when classified move metrics violate the aggregate contract."""


@dataclass(frozen=True)
class AccuracyPolicy:
    scale_centipawns: int = 100
    decimal_places: int = 2

    def __post_init__(self) -> None:
        if self.scale_centipawns < 1:
            raise ValueError("accuracy scale must be positive")
        if self.decimal_places != 2:
            raise ValueError("Prompt 10-H accuracy precision is fixed at two decimal places")

    def transform(self, acpl: Decimal) -> Decimal:
        if acpl < 0:
            raise ValueError("ACPL cannot be negative")
        scale = Decimal(self.scale_centipawns)
        return (HUNDRED * scale / (scale + acpl)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class MoveQualityCount:
    quality: MoveQuality
    count: int


@dataclass(frozen=True)
class PlayerAnalyticalSummary:
    color: chess.Color
    total_move_count: int
    cpl_eligible_move_count: int
    excluded_move_count: int
    cpl_coverage: Decimal | None
    summed_centipawn_loss: int
    acpl: Decimal | None
    accuracy_available: bool
    accuracy: Decimal | None
    classified_move_count: int
    unclassified_move_count: int
    classification_coverage_percent: Decimal | None
    quality_counts: tuple[MoveQualityCount, ...]


@dataclass(frozen=True)
class InternalGameAnalyticalAggregate:
    game_id: UUID
    analysis_run_id: UUID
    lease_generation: int
    white: PlayerAnalyticalSummary
    black: PlayerAnalyticalSummary


class GameMetricAggregationService:
    def __init__(self, accuracy_policy: AccuracyPolicy | None = None) -> None:
        self._accuracy_policy = accuracy_policy or AccuracyPolicy()

    def aggregate(
        self, classified: InternalClassifiedMoveMetrics
    ) -> InternalGameAnalyticalAggregate:
        plys = tuple(move.metric.ply for move in classified.moves)
        if len(set(plys)) != len(plys) or any(ply < 1 for ply in plys):
            raise GameMetricAggregationError("classified move plys must be unique and positive")
        white_moves = tuple(move for move in classified.moves if move.metric.mover == chess.WHITE)
        black_moves = tuple(move for move in classified.moves if move.metric.mover == chess.BLACK)
        if len(white_moves) + len(black_moves) != len(classified.moves):
            raise GameMetricAggregationError("classified move has an invalid mover color")
        return InternalGameAnalyticalAggregate(
            game_id=classified.game_id,
            analysis_run_id=classified.analysis_run_id,
            lease_generation=classified.lease_generation,
            white=self._summarize(chess.WHITE, white_moves),
            black=self._summarize(chess.BLACK, black_moves),
        )

    def _summarize(
        self,
        color: chess.Color,
        moves: tuple[ClassifiedMoveMetric, ...],
    ) -> PlayerAnalyticalSummary:
        eligible = tuple(
            move for move in moves if move.metric.outcome is MoveMetricOutcome.CENTIPAWN_LOSS
        )
        if any(move.metric.centipawn_loss is None for move in eligible):
            raise GameMetricAggregationError("eligible move is missing centipawn loss")
        summed_loss = sum(
            move.metric.centipawn_loss
            for move in eligible
            if move.metric.centipawn_loss is not None
        )
        eligible_count = len(eligible)
        acpl = (
            (Decimal(summed_loss) / Decimal(eligible_count)).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            if eligible_count
            else None
        )
        accuracy = self._accuracy_policy.transform(acpl) if acpl is not None else None
        quality_counts = tuple(
            MoveQualityCount(
                quality,
                sum(1 for move in moves if move.quality is quality),
            )
            for quality in MoveQuality
        )
        unclassified_count = sum(
            item.count for item in quality_counts if item.quality is MoveQuality.UNCLASSIFIED
        )
        classified_count = len(moves) - unclassified_count
        cpl_coverage = _percentage(eligible_count, len(moves))
        coverage = _percentage(classified_count, len(moves))
        return PlayerAnalyticalSummary(
            color=color,
            total_move_count=len(moves),
            cpl_eligible_move_count=eligible_count,
            excluded_move_count=len(moves) - eligible_count,
            cpl_coverage=cpl_coverage,
            summed_centipawn_loss=summed_loss,
            acpl=acpl,
            accuracy_available=accuracy is not None,
            accuracy=accuracy,
            classified_move_count=classified_count,
            unclassified_move_count=unclassified_count,
            classification_coverage_percent=coverage,
            quality_counts=quality_counts,
        )


def _percentage(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (HUNDRED * Decimal(numerator) / Decimal(denominator)).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
