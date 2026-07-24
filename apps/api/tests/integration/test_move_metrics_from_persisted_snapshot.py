from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.game_metrics import GameMetricAggregationService
from boardtrace_api.analysis.move_classification import (
    ClassificationReason,
    MoveClassificationService,
    MoveQuality,
)
from boardtrace_api.analysis.move_metrics import (
    MoveMetricDerivationService,
    MoveMetricOutcome,
)
from boardtrace_api.models import AnalysisMoveEvaluation, AnalysisPositionEvaluation, AnalysisRun
from boardtrace_api.services.analysis_reads import InternalAnalysisReadService
from tests.integration.test_internal_analysis_reads import _completed_snapshot

pytestmark = [pytest.mark.database, pytest.mark.integration]


@pytest.mark.asyncio
async def test_derives_metrics_from_authorized_current_postgres_snapshot_without_writes(
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    counts_before = (
        await auth_database_session.scalar(select(func.count(AnalysisRun.id))),
        await auth_database_session.scalar(select(func.count(AnalysisPositionEvaluation.id))),
        await auth_database_session.scalar(select(func.count(AnalysisMoveEvaluation.id))),
    )
    snapshot = await InternalAnalysisReadService(auth_database_session).read_for_owner(
        job.game_id, job.owner_user_id
    )

    derived = MoveMetricDerivationService().derive(snapshot)
    classified = MoveClassificationService().classify(derived)
    aggregate = GameMetricAggregationService().aggregate(classified)

    assert derived.game_id == job.game_id
    assert derived.analysis_run_id == snapshot.analysis.run_id
    assert derived.lease_generation == snapshot.analysis.lease_generation
    assert tuple(metric.ply for metric in derived.moves) == (1, 2)
    assert all(metric.outcome is MoveMetricOutcome.CENTIPAWN_LOSS for metric in derived.moves)
    assert tuple(metric.centipawn_delta for metric in derived.moves) == (-1, -3)
    assert tuple(metric.raw_centipawn_loss for metric in derived.moves) == (1, 3)
    assert tuple(metric.centipawn_loss for metric in derived.moves) == (1, 3)
    assert tuple(move.quality for move in classified.moves) == (
        MoveQuality.BEST,
        MoveQuality.BEST,
    )
    assert all(move.reason is ClassificationReason.BEST_MOVE_EQUALITY for move in classified.moves)
    assert classified.analysis_run_id == snapshot.analysis.run_id
    assert classified.lease_generation == snapshot.analysis.lease_generation
    assert aggregate.game_id == snapshot.game_id
    assert aggregate.analysis_run_id == snapshot.analysis.run_id
    assert aggregate.white.total_move_count == 1
    assert aggregate.white.cpl_eligible_move_count == 1
    assert aggregate.white.cpl_coverage == Decimal("100.00")
    assert aggregate.white.summed_centipawn_loss == 1
    assert aggregate.white.acpl == Decimal("1.00")
    assert aggregate.white.accuracy == Decimal("99.01")
    assert aggregate.black.total_move_count == 1
    assert aggregate.black.cpl_eligible_move_count == 1
    assert aggregate.black.cpl_coverage == Decimal("100.00")
    assert aggregate.black.summed_centipawn_loss == 3
    assert aggregate.black.acpl == Decimal("3.00")
    assert aggregate.black.accuracy == Decimal("97.09")
    assert aggregate.white.classification_coverage_percent == Decimal("100.00")
    assert aggregate.black.classification_coverage_percent == Decimal("100.00")
    assert not auth_database_session.new
    assert not auth_database_session.dirty
    assert not auth_database_session.deleted
    counts_after = (
        await auth_database_session.scalar(select(func.count(AnalysisRun.id))),
        await auth_database_session.scalar(select(func.count(AnalysisPositionEvaluation.id))),
        await auth_database_session.scalar(select(func.count(AnalysisMoveEvaluation.id))),
    )
    assert counts_after == counts_before
