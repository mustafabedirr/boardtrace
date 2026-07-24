"""Fail-closed internal composition of the complete analysis read pipeline."""

from dataclasses import dataclass
from uuid import UUID

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.game_metrics import (
    GameMetricAggregationService,
    InternalGameAnalyticalAggregate,
)
from boardtrace_api.analysis.move_classification import (
    InternalClassifiedMoveMetrics,
    MoveClassificationService,
)
from boardtrace_api.analysis.move_metrics import (
    InternalMoveMetrics,
    MoveMetricDerivationService,
)
from boardtrace_api.services.analysis_reads import (
    InternalAnalysisReadService,
    InternalAnalysisSnapshot,
)


class InternalAnalysisAggregateCompositionError(RuntimeError):
    """Raised when composed internal layers do not share one authoritative identity."""


@dataclass(frozen=True)
class UnifiedInternalAnalysisAggregate:
    """One immutable view over a single authorized authoritative snapshot."""

    game_id: UUID
    owner_user_id: UUID
    analysis_run_id: UUID
    lease_generation: int
    snapshot: InternalAnalysisSnapshot
    move_metrics: InternalMoveMetrics
    classifications: InternalClassifiedMoveMetrics
    game_metrics: InternalGameAnalyticalAggregate


class InternalAnalysisAggregateService:
    """Reads once, derives in memory, and validates the complete internal pipeline."""

    def __init__(self, session: AsyncSession) -> None:
        self._reader = InternalAnalysisReadService(session)
        self._metric_deriver = MoveMetricDerivationService()
        self._classifier = MoveClassificationService()
        self._aggregator = GameMetricAggregationService()

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> UnifiedInternalAnalysisAggregate:
        snapshot = await self._reader.read_for_owner(game_id, requesting_user_id)
        move_metrics = self._metric_deriver.derive(snapshot)
        classifications = self._classifier.classify(move_metrics)
        game_metrics = self._aggregator.aggregate(classifications)
        aggregate = UnifiedInternalAnalysisAggregate(
            game_id=snapshot.game_id,
            owner_user_id=snapshot.owner_user_id,
            analysis_run_id=snapshot.analysis.run_id,
            lease_generation=snapshot.analysis.lease_generation,
            snapshot=snapshot,
            move_metrics=move_metrics,
            classifications=classifications,
            game_metrics=game_metrics,
        )
        validate_internal_analysis_aggregate(aggregate)
        return aggregate


def validate_internal_analysis_aggregate(
    aggregate: UnifiedInternalAnalysisAggregate,
) -> None:
    """Reject identity, ordering, or linkage drift between any composed layer."""
    snapshot = aggregate.snapshot
    expected_identity = (
        aggregate.game_id,
        aggregate.analysis_run_id,
        aggregate.lease_generation,
    )
    identities = (
        (
            snapshot.game_id,
            snapshot.analysis.run_id,
            snapshot.analysis.lease_generation,
        ),
        (
            snapshot.analysis.result.game_id,
            snapshot.analysis.run_id,
            snapshot.analysis.lease_generation,
        ),
        (
            aggregate.move_metrics.game_id,
            aggregate.move_metrics.analysis_run_id,
            aggregate.move_metrics.lease_generation,
        ),
        (
            aggregate.classifications.game_id,
            aggregate.classifications.analysis_run_id,
            aggregate.classifications.lease_generation,
        ),
        (
            aggregate.game_metrics.game_id,
            aggregate.game_metrics.analysis_run_id,
            aggregate.game_metrics.lease_generation,
        ),
    )
    if aggregate.owner_user_id != snapshot.owner_user_id:
        raise InternalAnalysisAggregateCompositionError("snapshot owner identity drifted")
    if any(identity != expected_identity for identity in identities):
        raise InternalAnalysisAggregateCompositionError("analysis authority identity drifted")

    persisted_moves = snapshot.analysis.result.move_evaluations
    metric_moves = aggregate.move_metrics.moves
    classified_moves = aggregate.classifications.moves
    if len(persisted_moves) != len(metric_moves) or len(metric_moves) != len(classified_moves):
        raise InternalAnalysisAggregateCompositionError("analysis move cardinality drifted")
    for persisted, metric, classified in zip(
        persisted_moves,
        metric_moves,
        classified_moves,
        strict=True,
    ):
        if (persisted.ply, persisted.move_uci, persisted.move_san) != (
            metric.ply,
            metric.move_uci,
            metric.move_san,
        ) or classified.metric != metric:
            raise InternalAnalysisAggregateCompositionError("analysis move linkage drifted")

    white_count = sum(metric.mover == chess.WHITE for metric in metric_moves)
    black_count = sum(metric.mover == chess.BLACK for metric in metric_moves)
    white = aggregate.game_metrics.white
    black = aggregate.game_metrics.black
    if (
        white.color != chess.WHITE
        or black.color != chess.BLACK
        or white.total_move_count != white_count
        or black.total_move_count != black_count
        or white_count + black_count != len(metric_moves)
    ):
        raise InternalAnalysisAggregateCompositionError("player partition drifted")
    for summary in (white, black):
        if (
            sum(item.count for item in summary.quality_counts) != summary.total_move_count
            or summary.classified_move_count + summary.unclassified_move_count
            != summary.total_move_count
            or summary.cpl_eligible_move_count + summary.excluded_move_count
            != summary.total_move_count
        ):
            raise InternalAnalysisAggregateCompositionError("player summary totals drifted")
