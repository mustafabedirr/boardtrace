"""Pure internal move-quality classification over Prompt 10-F metrics."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import chess

from boardtrace_api.analysis.move_metrics import (
    InternalMoveMetrics,
    MoveAnalyticalMetric,
    MoveMetricOutcome,
)


class MoveClassificationError(ValueError):
    """Raised when a metric violates the closed classifier contract."""


class MoveQuality(StrEnum):
    BEST = "BEST"
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    INACCURACY = "INACCURACY"
    MISTAKE = "MISTAKE"
    BLUNDER = "BLUNDER"
    UNCLASSIFIED = "UNCLASSIFIED"


class ClassificationReason(StrEnum):
    FORCED_WIN_CREATED = "FORCED_WIN_CREATED"
    FORCED_WIN_LOST = "FORCED_WIN_LOST"
    FORCED_LOSS_ENTERED = "FORCED_LOSS_ENTERED"
    FORCED_LOSS_ESCAPED = "FORCED_LOSS_ESCAPED"
    MATE_POLARITY_FLIPPED_TO_WIN = "MATE_POLARITY_FLIPPED_TO_WIN"
    MATE_POLARITY_FLIPPED_TO_LOSS = "MATE_POLARITY_FLIPPED_TO_LOSS"
    FORCED_WIN_PRESERVED = "FORCED_WIN_PRESERVED"
    FORCED_LOSS_UNRESOLVED = "FORCED_LOSS_UNRESOLVED"
    BEST_MOVE_EQUALITY = "BEST_MOVE_EQUALITY"
    CENTIPAWN_THRESHOLD = "CENTIPAWN_THRESHOLD"
    SCORE_UNCLASSIFIED = "SCORE_UNCLASSIFIED"
    MATE_POLARITY_UNCLASSIFIED = "MATE_POLARITY_UNCLASSIFIED"


@dataclass(frozen=True)
class CentipawnLossThresholdPolicy:
    excellent_max: int = 20
    good_max: int = 50
    inaccuracy_max: int = 100
    mistake_max: int = 200

    def __post_init__(self) -> None:
        if not (0 <= self.excellent_max < self.good_max < self.inaccuracy_max < self.mistake_max):
            raise ValueError("centipawn-loss thresholds must be strictly increasing")

    def classify(self, loss: int) -> MoveQuality:
        if loss < 0:
            raise ValueError("clamped centipawn loss cannot be negative")
        if loss <= self.excellent_max:
            return MoveQuality.EXCELLENT
        if loss <= self.good_max:
            return MoveQuality.GOOD
        if loss <= self.inaccuracy_max:
            return MoveQuality.INACCURACY
        if loss <= self.mistake_max:
            return MoveQuality.MISTAKE
        return MoveQuality.BLUNDER


@dataclass(frozen=True)
class ClassifiedMoveMetric:
    metric: MoveAnalyticalMetric
    quality: MoveQuality
    reason: ClassificationReason
    best_move_equal: bool


@dataclass(frozen=True)
class InternalClassifiedMoveMetrics:
    game_id: UUID
    analysis_run_id: UUID
    lease_generation: int
    moves: tuple[ClassifiedMoveMetric, ...]


class MoveClassificationService:
    def __init__(self, policy: CentipawnLossThresholdPolicy | None = None) -> None:
        self._policy = policy or CentipawnLossThresholdPolicy()

    def classify(self, metrics: InternalMoveMetrics) -> InternalClassifiedMoveMetrics:
        return InternalClassifiedMoveMetrics(
            game_id=metrics.game_id,
            analysis_run_id=metrics.analysis_run_id,
            lease_generation=metrics.lease_generation,
            moves=tuple(self.classify_move(metric) for metric in metrics.moves),
        )

    def classify_move(self, metric: MoveAnalyticalMetric) -> ClassifiedMoveMetric:
        best_move_equal = _best_move_equal(metric)
        if metric.outcome is MoveMetricOutcome.CENTIPAWN_LOSS:
            _validate_centipawn_contract(metric)
        mate_decision = _mate_precedence(metric, best_move_equal)
        if mate_decision is not None:
            quality, reason = mate_decision
        elif metric.outcome is MoveMetricOutcome.MISSING_SCORE:
            quality, reason = (
                MoveQuality.UNCLASSIFIED,
                ClassificationReason.SCORE_UNCLASSIFIED,
            )
        elif best_move_equal:
            quality, reason = MoveQuality.BEST, ClassificationReason.BEST_MOVE_EQUALITY
        elif metric.outcome is MoveMetricOutcome.MATE_TO_MATE:
            quality, reason = _same_polarity_mate(metric)
        elif metric.outcome is MoveMetricOutcome.CENTIPAWN_LOSS:
            if metric.centipawn_loss is None:
                raise MoveClassificationError("centipawn metric is missing clamped loss")
            quality = self._policy.classify(metric.centipawn_loss)
            reason = ClassificationReason.CENTIPAWN_THRESHOLD
        else:
            quality, reason = (
                MoveQuality.UNCLASSIFIED,
                ClassificationReason.MATE_POLARITY_UNCLASSIFIED,
            )
        return ClassifiedMoveMetric(metric, quality, reason, best_move_equal)


def _best_move_equal(metric: MoveAnalyticalMetric) -> bool:
    reference = metric.reference_best_move_uci
    if reference is None:
        return False
    try:
        played = chess.Move.from_uci(metric.move_uci).uci()
        expected = chess.Move.from_uci(reference).uci()
    except ValueError as error:
        raise MoveClassificationError("best-move equality received invalid UCI") from error
    return played == expected


def _mate_precedence(
    metric: MoveAnalyticalMetric,
    best_move_equal: bool,
) -> tuple[MoveQuality, ClassificationReason] | None:
    before_mate = metric.before.mate_in
    after_mate = metric.after.mate_in
    if metric.outcome is MoveMetricOutcome.CENTIPAWN_TO_MATE:
        if after_mate is None or after_mate == 0:
            return MoveQuality.UNCLASSIFIED, ClassificationReason.MATE_POLARITY_UNCLASSIFIED
        if after_mate > 0:
            return (
                MoveQuality.BEST if best_move_equal else MoveQuality.EXCELLENT,
                ClassificationReason.FORCED_WIN_CREATED,
            )
        return MoveQuality.BLUNDER, ClassificationReason.FORCED_LOSS_ENTERED
    if metric.outcome is MoveMetricOutcome.MATE_TO_CENTIPAWN:
        if before_mate is None or before_mate == 0:
            return MoveQuality.UNCLASSIFIED, ClassificationReason.MATE_POLARITY_UNCLASSIFIED
        if before_mate > 0:
            return MoveQuality.BLUNDER, ClassificationReason.FORCED_WIN_LOST
        return (
            MoveQuality.BEST if best_move_equal else MoveQuality.EXCELLENT,
            ClassificationReason.FORCED_LOSS_ESCAPED,
        )
    if metric.outcome is not MoveMetricOutcome.MATE_TO_MATE:
        return None
    if before_mate is None or after_mate is None or before_mate == 0 or after_mate == 0:
        return MoveQuality.UNCLASSIFIED, ClassificationReason.MATE_POLARITY_UNCLASSIFIED
    if before_mate > 0 and after_mate < 0:
        return MoveQuality.BLUNDER, ClassificationReason.MATE_POLARITY_FLIPPED_TO_LOSS
    if before_mate < 0 and after_mate > 0:
        return (
            MoveQuality.BEST if best_move_equal else MoveQuality.EXCELLENT,
            ClassificationReason.MATE_POLARITY_FLIPPED_TO_WIN,
        )
    return None


def _same_polarity_mate(
    metric: MoveAnalyticalMetric,
) -> tuple[MoveQuality, ClassificationReason]:
    before_mate = metric.before.mate_in
    after_mate = metric.after.mate_in
    if before_mate is None or after_mate is None or before_mate == 0 or after_mate == 0:
        return MoveQuality.UNCLASSIFIED, ClassificationReason.MATE_POLARITY_UNCLASSIFIED
    if before_mate > 0 and after_mate > 0:
        return MoveQuality.GOOD, ClassificationReason.FORCED_WIN_PRESERVED
    if before_mate < 0 and after_mate < 0:
        return MoveQuality.GOOD, ClassificationReason.FORCED_LOSS_UNRESOLVED
    raise MoveClassificationError("mate polarity transition bypassed precedence")


def _validate_centipawn_contract(metric: MoveAnalyticalMetric) -> None:
    if (
        metric.centipawn_delta is None
        or metric.raw_centipawn_loss is None
        or metric.centipawn_loss is None
        or metric.raw_centipawn_loss != -metric.centipawn_delta
        or metric.centipawn_loss != max(0, metric.raw_centipawn_loss)
        or metric.negative_loss_clamped != (metric.raw_centipawn_loss < 0)
    ):
        raise MoveClassificationError("centipawn metric fields are inconsistent")
