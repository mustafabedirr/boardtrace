from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AnalysisJob, AnalysisPositionEvaluation, AnalysisRun, Game
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisJobType, GameStatus
from boardtrace_api.services.analysis_reads import (
    AnalysisGameNotFoundError,
    AnalysisReadForbiddenError,
    AnalysisSnapshotCorruptError,
    AnalysisSnapshotUnavailableError,
    InternalAnalysisReadService,
)
from boardtrace_api.services.analysis_results import AnalysisResultPersistenceService
from tests.integration.test_analysis_result_persistence import (
    _configuration,
    _result,
    _running_job,
)

pytestmark = [pytest.mark.database, pytest.mark.integration]


async def _completed_snapshot(session: AsyncSession) -> tuple[AnalysisJob, AnalysisRun]:
    job = await _running_job(session)
    now = datetime.now(UTC)
    run = await AnalysisResultPersistenceService(session).persist_and_complete_owned_generation(
        job_id=job.id,
        worker_id="worker-a",
        lease_generation=job.lease_generation,
        result=_result(job.game_id),
        configuration=_configuration(),
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )
    return job, run


@pytest.mark.asyncio
async def test_owner_reads_current_complete_snapshot_in_durable_order(
    auth_database_session: AsyncSession,
) -> None:
    job, run = await _completed_snapshot(auth_database_session)

    snapshot = await InternalAnalysisReadService(auth_database_session).read_for_owner(
        job.game_id, job.owner_user_id
    )

    assert snapshot.game_id == job.game_id
    assert snapshot.owner_user_id == job.owner_user_id
    assert snapshot.analysis.run_id == run.id
    assert snapshot.analysis.lease_generation == job.lease_generation
    assert tuple(item.ply for item in snapshot.analysis.result.position_evaluations) == (0, 1, 2)
    assert tuple(item.ply for item in snapshot.analysis.result.move_evaluations) == (1, 2)
    assert all(not hasattr(item, "fen") for item in snapshot.analysis.result.position_evaluations)


@pytest.mark.asyncio
async def test_not_found_forbidden_and_unavailable_are_distinct(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    service = InternalAnalysisReadService(auth_database_session)

    with pytest.raises(AnalysisGameNotFoundError):
        await service.read_for_owner(uuid4(), job.owner_user_id)
    with pytest.raises(AnalysisReadForbiddenError):
        await service.read_for_owner(job.game_id, uuid4())
    with pytest.raises(AnalysisSnapshotUnavailableError):
        await service.read_for_owner(job.game_id, job.owner_user_id)

    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.CAPTURING
    await auth_database_session.commit()
    with pytest.raises(AnalysisSnapshotUnavailableError):
        await service.read_for_owner(job.game_id, job.owner_user_id)


@pytest.mark.asyncio
async def test_forbidden_access_queries_authority_before_snapshot_tables(
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
            await InternalAnalysisReadService(auth_database_session).read_for_owner(
                job.game_id, uuid4()
            )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert statements
    assert " from games " in " ".join(statements).replace("\n", " ")
    assert all("analysis_runs" not in statement for statement in statements)
    assert all("analysis_position_evaluations" not in statement for statement in statements)
    assert all("analysis_move_evaluations" not in statement for statement in statements)


@pytest.mark.asyncio
async def test_newer_nonterminal_job_blocks_fallback_to_old_complete_run(
    auth_database_session: AsyncSession,
) -> None:
    old_job, _ = await _completed_snapshot(auth_database_session)
    newer = AnalysisJob(
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
    auth_database_session.add(newer)
    await auth_database_session.commit()

    with pytest.raises(AnalysisSnapshotUnavailableError):
        await InternalAnalysisReadService(auth_database_session).read_for_owner(
            old_job.game_id, old_job.owner_user_id
        )
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1


@pytest.mark.asyncio
async def test_corrupt_current_snapshot_fails_closed(
    auth_database_session: AsyncSession,
) -> None:
    job, run = await _completed_snapshot(auth_database_session)
    run.configuration_snapshot = {"schema_version": 1}
    await auth_database_session.commit()

    with pytest.raises(AnalysisSnapshotCorruptError):
        await InternalAnalysisReadService(auth_database_session).read_for_owner(
            job.game_id, job.owner_user_id
        )


@pytest.mark.asyncio
async def test_invalid_durable_position_value_is_not_silently_coerced(
    auth_database_session: AsyncSession,
) -> None:
    job, run = await _completed_snapshot(auth_database_session)
    await auth_database_session.execute(
        update(AnalysisPositionEvaluation)
        .where(
            AnalysisPositionEvaluation.analysis_run_id == run.id,
            AnalysisPositionEvaluation.ply == 0,
        )
        .values(side_to_move="x")
    )
    await auth_database_session.commit()

    with pytest.raises(AnalysisSnapshotCorruptError):
        await InternalAnalysisReadService(auth_database_session).read_for_owner(
            job.game_id, job.owner_user_id
        )
