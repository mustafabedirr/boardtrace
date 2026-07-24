from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import (
    AnalysisJob,
    AnalysisMoveEvaluation,
    AnalysisPositionEvaluation,
    AnalysisRun,
)
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisJobType
from boardtrace_api.services.analysis_aggregates import (
    InternalAnalysisAggregateCompositionError,
    InternalAnalysisAggregateService,
    validate_internal_analysis_aggregate,
)
from boardtrace_api.services.analysis_facade import (
    InternalAnalysisReadFacade,
    compose_internal_analysis_read_facade,
)
from boardtrace_api.services.analysis_reads import (
    AnalysisReadForbiddenError,
    AnalysisSnapshotUnavailableError,
)
from boardtrace_api.services.analysis_results import AnalysisResultPersistenceService
from tests.integration.test_analysis_result_persistence import _configuration, _result
from tests.integration.test_internal_analysis_reads import _completed_snapshot

pytestmark = [pytest.mark.database, pytest.mark.integration]


async def _record_counts(session: AsyncSession) -> tuple[int | None, ...]:
    return (
        await session.scalar(select(func.count(AnalysisRun.id))),
        await session.scalar(select(func.count(AnalysisPositionEvaluation.id))),
        await session.scalar(select(func.count(AnalysisMoveEvaluation.id))),
    )


@pytest.mark.asyncio
async def test_composes_one_authorized_snapshot_end_to_end_without_writes(
    auth_database_session: AsyncSession,
) -> None:
    job, run = await _completed_snapshot(auth_database_session)
    counts_before = await _record_counts(auth_database_session)

    result = await InternalAnalysisAggregateService(auth_database_session).read_for_owner(
        job.game_id, job.owner_user_id
    )

    assert result.game_id == job.game_id
    assert result.owner_user_id == job.owner_user_id
    assert result.analysis_run_id == run.id
    assert result.lease_generation == job.lease_generation
    assert result.snapshot.analysis.run_id == result.analysis_run_id
    assert result.move_metrics.analysis_run_id == result.analysis_run_id
    assert result.classifications.analysis_run_id == result.analysis_run_id
    assert result.game_metrics.analysis_run_id == result.analysis_run_id
    assert tuple(move.ply for move in result.move_metrics.moves) == (1, 2)
    assert tuple(item.metric for item in result.classifications.moves) == result.move_metrics.moves
    assert result.game_metrics.white.total_move_count == 1
    assert result.game_metrics.white.cpl_coverage == Decimal("100.00")
    assert result.game_metrics.black.total_move_count == 1
    assert result.game_metrics.black.cpl_coverage == Decimal("100.00")
    assert not auth_database_session.new
    assert not auth_database_session.dirty
    assert not auth_database_session.deleted
    assert await _record_counts(auth_database_session) == counts_before


@pytest.mark.asyncio
async def test_authorization_fails_before_composition(
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)

    with pytest.raises(AnalysisReadForbiddenError):
        await InternalAnalysisAggregateService(auth_database_session).read_for_owner(
            job.game_id,
            uuid4(),
        )


@pytest.mark.asyncio
async def test_facade_authorization_failure_short_circuits_result_tables(
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    statements: list[str] = []
    bind = auth_database_session.get_bind()

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.casefold())

    event.listen(bind, "before_cursor_execute", capture_statement)
    try:
        with pytest.raises(AnalysisReadForbiddenError):
            await compose_internal_analysis_read_facade(auth_database_session).read_for_owner(
                job.game_id, uuid4()
            )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    combined = " ".join(statements).replace("\n", " ")
    assert " from games " in combined
    assert "analysis_jobs" not in combined
    assert "analysis_runs" not in combined
    assert "analysis_position_evaluations" not in combined
    assert "analysis_move_evaluations" not in combined


def test_provider_resolves_a_fresh_exact_internal_facade_chain(
    auth_database_session: AsyncSession,
) -> None:
    first = compose_internal_analysis_read_facade(auth_database_session)
    second = compose_internal_analysis_read_facade(auth_database_session)

    assert isinstance(first, InternalAnalysisReadFacade)
    assert isinstance(first._aggregate_service, InternalAnalysisAggregateService)
    assert first is not second
    assert first._aggregate_service is not second._aggregate_service


@pytest.mark.asyncio
async def test_facade_selects_only_current_authoritative_run_without_layer_mixing(
    auth_database_session: AsyncSession,
) -> None:
    old_job, old_run = await _completed_snapshot(auth_database_session)
    current_job = AnalysisJob(
        game_id=old_job.game_id,
        owner_user_id=old_job.owner_user_id,
        position_id=None,
        job_type=AnalysisJobType.REPORT,
        status=AnalysisJobStatus.RUNNING,
        attempts=1,
        attempt_count=1,
        max_attempts=3,
        analysis_profile="standard",
        analysis_version=2,
        lease_generation=1,
        worker_id="worker-current",
    )
    auth_database_session.add(current_job)
    await auth_database_session.commit()
    now = datetime.now(UTC)
    current_run = await AnalysisResultPersistenceService(
        auth_database_session
    ).persist_and_complete_owned_generation(
        job_id=current_job.id,
        worker_id="worker-current",
        lease_generation=1,
        result=_result(old_job.game_id, score_offset=50),
        configuration=_configuration(),
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )

    result = await compose_internal_analysis_read_facade(auth_database_session).read_for_owner(
        old_job.game_id, old_job.owner_user_id
    )

    assert old_run.id != current_run.id
    assert result.analysis_run_id == current_run.id
    assert result.snapshot.analysis.analysis_version == 2
    assert result.snapshot.analysis.result.position_evaluations[0].score.centipawns == 50
    assert {
        result.move_metrics.analysis_run_id,
        result.classifications.analysis_run_id,
        result.game_metrics.analysis_run_id,
    } == {current_run.id}


@pytest.mark.asyncio
async def test_facade_never_falls_back_to_historical_run(
    auth_database_session: AsyncSession,
) -> None:
    old_job, _ = await _completed_snapshot(auth_database_session)
    auth_database_session.add(
        AnalysisJob(
            game_id=old_job.game_id,
            owner_user_id=old_job.owner_user_id,
            position_id=None,
            job_type=AnalysisJobType.REPORT,
            status=AnalysisJobStatus.PENDING,
            attempts=0,
            attempt_count=0,
            max_attempts=3,
            analysis_profile="standard",
            analysis_version=2,
            lease_generation=0,
        )
    )
    await auth_database_session.commit()

    with pytest.raises(AnalysisSnapshotUnavailableError):
        await compose_internal_analysis_read_facade(auth_database_session).read_for_owner(
            old_job.game_id, old_job.owner_user_id
        )


@pytest.mark.asyncio
async def test_cross_layer_identity_tampering_fails_closed(
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    result = await InternalAnalysisAggregateService(auth_database_session).read_for_owner(
        job.game_id, job.owner_user_id
    )
    tampered = replace(
        result,
        move_metrics=replace(result.move_metrics, analysis_run_id=uuid4()),
    )

    with pytest.raises(
        InternalAnalysisAggregateCompositionError,
        match="authority identity",
    ):
        validate_internal_analysis_aggregate(tampered)


@pytest.mark.asyncio
async def test_cross_layer_move_linkage_tampering_fails_closed(
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    result = await InternalAnalysisAggregateService(auth_database_session).read_for_owner(
        job.game_id, job.owner_user_id
    )
    reversed_classifications = replace(
        result.classifications,
        moves=tuple(reversed(result.classifications.moves)),
    )

    with pytest.raises(
        InternalAnalysisAggregateCompositionError,
        match="move linkage",
    ):
        validate_internal_analysis_aggregate(
            replace(result, classifications=reversed_classifications)
        )
