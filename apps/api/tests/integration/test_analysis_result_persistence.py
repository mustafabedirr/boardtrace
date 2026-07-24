import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import chess
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.analysis.full_game import (
    AnalysisCheckpoint,
    EngineReusePolicy,
    FullGameAnalysisResult,
    FullGameAnalysisStatus,
    FullGameFailure,
    FullGameFailureCode,
    MoveEvaluation,
    PositionEvaluation,
)
from boardtrace_api.analysis.stockfish import StockfishScore
from boardtrace_api.db.transactions import BeforeCommitHook, TransactionBoundary
from boardtrace_api.models import (
    AnalysisJob,
    AnalysisMoveEvaluation,
    AnalysisPositionEvaluation,
    AnalysisRun,
    Game,
    User,
)
from boardtrace_api.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
    GameResult,
    GameStatus,
    PlayerColor,
)
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.repositories.analysis_results import (
    AnalysisResultNotCompleteError,
    AnalysisRunAuthorityError,
    analysis_run_id,
    move_evaluation_id,
    position_evaluation_id,
)
from boardtrace_api.services.analysis_results import (
    AnalysisResultPersistenceService,
    EngineConfigurationSnapshot,
    PersistedCompleteAnalysisResult,
)

pytestmark = [pytest.mark.database, pytest.mark.integration]


async def _running_job(session: AsyncSession, generation: int = 1) -> AnalysisJob:
    user = User(
        email=f"result-{uuid4()}@example.test",
        normalized_email=f"result-{uuid4()}@example.test",
        display_name=None,
        password_hash=None,
    )
    session.add(user)
    await session.flush()
    game = Game(
        user_id=user.id,
        status=GameStatus.FINISHED,
        platform="test",
        player_color=PlayerColor.UNKNOWN,
        result=GameResult.UNKNOWN,
        completion_verified_at=datetime.now(UTC),
        normalized_moves=["e2e4", "e7e5"],
        source_game_id=str(uuid4()),
    )
    session.add(game)
    await session.flush()
    job = AnalysisJob(
        game_id=game.id,
        owner_user_id=user.id,
        position_id=None,
        job_type=AnalysisJobType.REPORT,
        status=AnalysisJobStatus.RUNNING,
        attempts=1,
        attempt_count=1,
        max_attempts=3,
        analysis_profile="standard",
        analysis_version=1,
        lease_generation=generation,
        worker_id="worker-a",
    )
    session.add(job)
    await session.commit()
    return job


def _result(game_id: UUID, score_offset: int = 0) -> FullGameAnalysisResult:
    positions = tuple(
        PositionEvaluation(
            position_id=uuid4(),
            ply=ply,
            fen=fen,
            side_to_move=side,
            score=StockfishScore(centipawns=score_offset + ply),
            best_move_uci=best,
            principal_variation_uci=(best,),
            depth=8,
            nodes=100 + ply,
            time_ms=10 + ply,
        )
        for ply, fen, side, best in (
            (0, chess.Board().fen(), chess.WHITE, "e2e4"),
            (
                1,
                "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                chess.BLACK,
                "e7e5",
            ),
            (
                2,
                "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                chess.WHITE,
                "g1f3",
            ),
        )
    )
    moves = (
        MoveEvaluation(1, "e2e4", "e4", positions[0], positions[1]),
        MoveEvaluation(2, "e7e5", "e5", positions[1], positions[2]),
    )
    return FullGameAnalysisResult(
        game_id=game_id,
        status=FullGameAnalysisStatus.COMPLETE,
        position_evaluations=positions,
        move_evaluations=moves,
        checkpoint=AnalysisCheckpoint(2, 3, 2, 3, 2),
        engine_name="Stockfish",
        engine_version="17",
        engine_reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
    )


def _configuration() -> EngineConfigurationSnapshot:
    return EngineConfigurationSnapshot(
        schema_version=1,
        depth=8,
        max_position_time_ms=500,
        max_game_time_ms=5_000,
        max_positions=3,
        max_moves=2,
        threads=1,
        hash_mb=16,
        command_timeout_ms=5_000,
        reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
    )


def _assert_minimized_read_back(
    durable: PersistedCompleteAnalysisResult, source: FullGameAnalysisResult
) -> None:
    assert durable.game_id == source.game_id
    assert durable.status == source.status
    assert durable.checkpoint == source.checkpoint
    assert durable.engine_name == source.engine_name
    assert durable.engine_version == source.engine_version
    assert durable.engine_reuse_policy == source.engine_reuse_policy
    assert len(durable.position_evaluations) == len(source.position_evaluations)
    for actual, expected in zip(
        durable.position_evaluations, source.position_evaluations, strict=True
    ):
        assert actual.position_id == expected.position_id
        assert actual.ply == expected.ply
        assert actual.side_to_move == expected.side_to_move
        assert actual.score == expected.score
        assert actual.best_move_uci == expected.best_move_uci
        assert actual.principal_variation_uci == expected.principal_variation_uci
        assert actual.depth == expected.depth
        assert actual.nodes == expected.nodes
        assert actual.time_ms == expected.time_ms
        assert not hasattr(actual, "fen")
    assert len(durable.move_evaluations) == len(source.move_evaluations)
    for actual_move, expected_move in zip(
        durable.move_evaluations, source.move_evaluations, strict=True
    ):
        assert actual_move.ply == expected_move.ply
        assert actual_move.move_uci == expected_move.move_uci
        assert actual_move.move_san == expected_move.move_san
        assert actual_move.before.ply == expected_move.before.ply
        assert actual_move.after.ply == expected_move.after.ply


@pytest.mark.asyncio
async def test_worker_finalization_atomically_persists_and_completes_job(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    now = datetime.now(UTC)

    run = await AnalysisResultPersistenceService(
        auth_database_session
    ).persist_and_complete_owned_generation(
        job_id=job.id,
        worker_id="worker-a",
        lease_generation=job.lease_generation,
        result=_result(job.game_id),
        configuration=_configuration(),
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )

    await auth_database_session.refresh(job)
    assert run.analysis_job_id == job.id
    assert job.status is AnalysisJobStatus.SUCCEEDED
    assert job.worker_id is None
    assert job.completed_at == now + timedelta(seconds=1)
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1


@pytest.mark.asyncio
async def test_worker_finalization_rolls_back_result_and_completion_together(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    now = datetime.now(UTC)

    async def reject_commit() -> None:
        raise RuntimeError("injected final commit failure")

    with pytest.raises(RuntimeError, match="injected final commit failure"):
        await AnalysisResultPersistenceService(
            auth_database_session
        ).persist_and_complete_owned_generation(
            job_id=job.id,
            worker_id="worker-a",
            lease_generation=job.lease_generation,
            result=_result(job.game_id),
            configuration=_configuration(),
            started_at=now,
            finished_at=now + timedelta(seconds=1),
            before_commit=reject_commit,
        )

    await auth_database_session.refresh(job)
    assert job.status is AnalysisJobStatus.RUNNING
    assert job.worker_id == "worker-a"
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0


@pytest.mark.asyncio
async def test_persists_ordered_records_and_idempotently_replaces_same_generation(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session)
    service = AnalysisResultPersistenceService(auth_database_session)
    started_at = datetime.now(UTC)
    first = await service.persist_owned_generation(
        job_id=job.id,
        worker_id="worker-a",
        lease_generation=1,
        result=_result(job.game_id),
        configuration=_configuration(),
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=1),
    )
    expected_run_id = analysis_run_id(job.id, 1)
    assert first.id == expected_run_id
    positions = list(
        await auth_database_session.scalars(
            select(AnalysisPositionEvaluation)
            .where(AnalysisPositionEvaluation.analysis_run_id == first.id)
            .order_by(AnalysisPositionEvaluation.ply)
        )
    )
    moves = list(
        await auth_database_session.scalars(
            select(AnalysisMoveEvaluation)
            .where(AnalysisMoveEvaluation.analysis_run_id == first.id)
            .order_by(AnalysisMoveEvaluation.ply)
        )
    )
    assert [item.ply for item in positions] == [0, 1, 2]
    assert [item.id for item in positions] == [
        position_evaluation_id(first.id, ply) for ply in range(3)
    ]
    assert [item.id for item in moves] == [move_evaluation_id(first.id, ply) for ply in range(1, 3)]
    assert moves[0].before_position_evaluation_id == positions[0].id
    assert moves[0].after_position_evaluation_id == positions[1].id
    assert first.configuration_snapshot["reuse_policy"] == "SINGLE_PROCESS_PER_GAME"

    replacement_result = _result(job.game_id, score_offset=50)
    replacement = await service.persist_owned_generation(
        job_id=job.id,
        worker_id="worker-a",
        lease_generation=1,
        result=replacement_result,
        configuration=_configuration(),
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=2),
    )
    assert replacement.id == first.id
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1
    assert (
        await auth_database_session.scalar(select(func.count(AnalysisPositionEvaluation.id))) == 3
    )
    assert await auth_database_session.scalar(select(func.count(AnalysisMoveEvaluation.id))) == 2
    replaced_initial = await auth_database_session.get(
        AnalysisPositionEvaluation, position_evaluation_id(first.id, 0)
    )
    assert replaced_initial is not None
    assert replaced_initial.centipawns == 50

    async with auth_sessionmaker() as fresh_session:
        read_back = await AnalysisResultPersistenceService(fresh_session).read_generation(job.id, 1)
        assert read_back is not None
        assert read_back.run_id == first.id
        _assert_minimized_read_back(read_back.result, replacement_result)
        assert read_back.configuration == _configuration()
        assert read_back.started_at == started_at
        assert read_back.finished_at == started_at + timedelta(seconds=2)

        column_names = set(
            (
                await fresh_session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'analysis_position_evaluations'"
                    )
                )
            ).scalars()
        )
        assert "fen" not in column_names

        durable_payloads = list(
            (
                await fresh_session.execute(
                    text("SELECT row_to_json(record)::text FROM analysis_runs AS record")
                )
            ).scalars()
        )
        durable_payloads.extend(
            (
                await fresh_session.execute(
                    text(
                        "SELECT row_to_json(record)::text "
                        "FROM analysis_position_evaluations AS record"
                    )
                )
            ).scalars()
        )
        durable_payloads.extend(
            (
                await fresh_session.execute(
                    text(
                        "SELECT row_to_json(record)::text FROM analysis_move_evaluations AS record"
                    )
                )
            ).scalars()
        )
        serialized = "\n".join(durable_payloads)
        assert all(
            position.fen not in serialized for position in replacement_result.position_evaluations
        )

    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    await auth_database_session.delete(game)
    await auth_database_session.commit()
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0
    assert (
        await auth_database_session.scalar(select(func.count(AnalysisPositionEvaluation.id))) == 0
    )
    assert await auth_database_session.scalar(select(func.count(AnalysisMoveEvaluation.id))) == 0


@pytest.mark.asyncio
async def test_generation_authority_rejects_stale_owner_and_versions_new_generation(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    service = AnalysisResultPersistenceService(auth_database_session)
    now = datetime.now(UTC)
    first = await service.persist_owned_generation(
        job_id=job.id,
        worker_id="worker-a",
        lease_generation=1,
        result=_result(job.game_id),
        configuration=_configuration(),
        started_at=now,
        finished_at=now,
    )
    first_id = first.id
    job_id = job.id
    game_id = job.game_id

    with pytest.raises(AnalysisRunAuthorityError):
        await service.persist_owned_generation(
            job_id=job_id,
            worker_id="stale-worker",
            lease_generation=1,
            result=_result(game_id),
            configuration=_configuration(),
            started_at=now,
            finished_at=now,
        )
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1

    refreshed_job = await auth_database_session.get(AnalysisJob, job_id)
    assert refreshed_job is not None
    refreshed_job.worker_id = "worker-b"
    refreshed_job.lease_generation = 2
    await auth_database_session.commit()
    second = await service.persist_owned_generation(
        job_id=job_id,
        worker_id="worker-b",
        lease_generation=2,
        result=_result(game_id, score_offset=10),
        configuration=_configuration(),
        started_at=now,
        finished_at=now,
    )
    assert second.id != first_id
    assert second.id == analysis_run_id(job_id, 2)
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 2


@pytest.mark.asyncio
async def test_non_complete_results_are_never_durable_and_transaction_failure_rolls_back(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    complete = _result(job.game_id)
    now = datetime.now(UTC)
    service = AnalysisResultPersistenceService(auth_database_session)
    for code, error_type in (
        (FullGameFailureCode.ENGINE_EXECUTION_FAILED, "StockfishExecutionError"),
        (FullGameFailureCode.ENGINE_EXECUTION_FAILED, "CancelledError"),
        (FullGameFailureCode.ENGINE_EXECUTION_FAILED, "AnalysisFailed"),
        (FullGameFailureCode.GAME_BUDGET_EXHAUSTED, "GameBudgetExhausted"),
    ):
        partial = replace(
            complete,
            status=FullGameAnalysisStatus.PARTIAL,
            position_evaluations=complete.position_evaluations[:2],
            move_evaluations=complete.move_evaluations[:1],
            checkpoint=AnalysisCheckpoint(2, 3, 1, 2, 1),
            failure=FullGameFailure(code, 2, error_type),
        )
        with pytest.raises(AnalysisResultNotCompleteError):
            await service.persist_owned_generation(
                job_id=job.id,
                worker_id="worker-a",
                lease_generation=1,
                result=partial,
                configuration=_configuration(),
                started_at=now,
                finished_at=now,
            )
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0

    async def fail_before_commit() -> None:
        raise RuntimeError("forced transaction failure")

    with pytest.raises(RuntimeError, match="forced transaction failure"):
        await service.persist_owned_generation(
            job_id=job.id,
            worker_id="worker-a",
            lease_generation=1,
            result=complete,
            configuration=_configuration(),
            started_at=now,
            finished_at=now,
            before_commit=fail_before_commit,
        )
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0


@pytest.mark.asyncio
async def test_live_game_state_rejects_result_persistence_before_any_write(
    auth_database_session: AsyncSession,
) -> None:
    job = await _running_job(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.CAPTURING
    game.completion_verified_at = None
    await auth_database_session.commit()
    now = datetime.now(UTC)

    with pytest.raises(AnalysisRunAuthorityError):
        await AnalysisResultPersistenceService(auth_database_session).persist_owned_generation(
            job_id=job.id,
            worker_id="worker-a",
            lease_generation=1,
            result=_result(job.game_id),
            configuration=_configuration(),
            started_at=now,
            finished_at=now,
        )

    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0


async def _persist_in_new_session(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    game_id: UUID,
    worker_id: str,
    generation: int,
    score_offset: int,
    before_commit: BeforeCommitHook | None = None,
) -> AnalysisRun:
    async with session_factory() as session:
        service = AnalysisResultPersistenceService(session)
        now = datetime.now(UTC)
        if before_commit is None:
            return await service.persist_owned_generation(
                job_id=job_id,
                worker_id=worker_id,
                lease_generation=generation,
                result=_result(game_id, score_offset),
                configuration=_configuration(),
                started_at=now,
                finished_at=now,
            )
        return await service.persist_owned_generation(
            job_id=job_id,
            worker_id=worker_id,
            lease_generation=generation,
            result=_result(game_id, score_offset),
            configuration=_configuration(),
            started_at=now,
            finished_at=now,
            before_commit=before_commit,
        )


@pytest.mark.asyncio
async def test_concurrent_identical_result_is_one_idempotent_generation(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session)
    job_id, game_id = job.id, job.game_id
    first_staged = asyncio.Event()
    release_first = asyncio.Event()

    async def block_first_commit() -> None:
        first_staged.set()
        await release_first.wait()

    first_task = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=7,
            before_commit=block_first_commit,
        )
    )
    await asyncio.wait_for(first_staged.wait(), timeout=2)
    second_task = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=7,
        )
    )
    await asyncio.sleep(0.1)
    assert not second_task.done()
    release_first.set()
    first, second = await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=5)

    assert first.id == second.id == analysis_run_id(job_id, 1)
    async with auth_sessionmaker() as fresh_session:
        assert await fresh_session.scalar(select(func.count(AnalysisRun.id))) == 1
        assert await fresh_session.scalar(select(func.count(AnalysisPositionEvaluation.id))) == 3
        assert await fresh_session.scalar(select(func.count(AnalysisMoveEvaluation.id))) == 2


@pytest.mark.asyncio
async def test_concurrent_different_result_replacement_has_lock_ordered_winner(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session)
    job_id, game_id = job.id, job.game_id
    first_staged = asyncio.Event()
    release_first = asyncio.Event()

    async def block_first_commit() -> None:
        first_staged.set()
        await release_first.wait()

    first_task = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=10,
            before_commit=block_first_commit,
        )
    )
    await asyncio.wait_for(first_staged.wait(), timeout=2)
    second_task = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=20,
        )
    )
    await asyncio.sleep(0.1)
    assert not second_task.done()
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=5)

    async with auth_sessionmaker() as fresh_session:
        read_back = await AnalysisResultPersistenceService(fresh_session).read_generation(job_id, 1)
        assert read_back is not None
        assert read_back.result.position_evaluations[0].score.centipawns == 20


@pytest.mark.asyncio
async def test_stale_generation_race_cannot_overwrite_current_authority(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session, generation=2)
    job.worker_id = "worker-current"
    await auth_database_session.commit()
    job_id, game_id = job.id, job.game_id
    stale_locked = asyncio.Event()
    release_stale = asyncio.Event()

    async def stale_attempt() -> None:
        async with auth_sessionmaker() as session:
            await session.scalar(
                select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
            )
            stale_locked.set()
            await release_stale.wait()
            with pytest.raises(AnalysisRunAuthorityError):
                await AnalysisResultPersistenceService(session).persist_owned_generation(
                    job_id=job_id,
                    worker_id="worker-stale",
                    lease_generation=1,
                    result=_result(game_id, 90),
                    configuration=_configuration(),
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )

    stale_task = asyncio.create_task(stale_attempt())
    await asyncio.wait_for(stale_locked.wait(), timeout=2)
    current_task = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-current",
            generation=2,
            score_offset=30,
        )
    )
    await asyncio.sleep(0.1)
    assert not current_task.done()
    release_stale.set()
    await asyncio.wait_for(asyncio.gather(stale_task, current_task), timeout=5)

    async with auth_sessionmaker() as fresh_session:
        assert (
            await AnalysisResultPersistenceService(fresh_session).read_generation(job_id, 1) is None
        )
        current = await AnalysisResultPersistenceService(fresh_session).read_generation(job_id, 2)
        assert current is not None
        assert current.result.position_evaluations[0].score.centipawns == 30


async def _complete_job_in_new_session(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    before_commit: BeforeCommitHook | None = None,
) -> bool:
    async with session_factory() as session:
        repository = AnalysisJobRepository(session)
        now = datetime.now(UTC)
        if before_commit is None:
            return await TransactionBoundary(session).execute(
                lambda: repository.complete_job(job_id, "worker-a", now, 1)
            )
        return await TransactionBoundary(session, before_commit).execute(
            lambda: repository.complete_job(job_id, "worker-a", now, 1)
        )


@pytest.mark.asyncio
async def test_persistence_wins_job_completion_race_then_completion_succeeds(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session)
    job_id, game_id = job.id, job.game_id
    persistence_staged = asyncio.Event()
    release_persistence = asyncio.Event()

    async def block_persistence() -> None:
        persistence_staged.set()
        await release_persistence.wait()

    persistence = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=0,
            before_commit=block_persistence,
        )
    )
    await asyncio.wait_for(persistence_staged.wait(), timeout=2)
    completion = asyncio.create_task(_complete_job_in_new_session(auth_sessionmaker, job_id))
    await asyncio.sleep(0.1)
    assert not completion.done()
    release_persistence.set()
    _, completed = await asyncio.wait_for(asyncio.gather(persistence, completion), timeout=5)
    assert completed is True

    async with auth_sessionmaker() as fresh_session:
        assert await AnalysisResultPersistenceService(fresh_session).read_generation(job_id, 1)
        terminal_job = await fresh_session.get(AnalysisJob, job_id)
        assert terminal_job is not None
        assert terminal_job.status is AnalysisJobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_job_completion_wins_race_and_late_persistence_is_rejected(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    job = await _running_job(auth_database_session)
    job_id, game_id = job.id, job.game_id
    completion_staged = asyncio.Event()
    release_completion = asyncio.Event()

    async def block_completion() -> None:
        completion_staged.set()
        await release_completion.wait()

    completion = asyncio.create_task(
        _complete_job_in_new_session(auth_sessionmaker, job_id, block_completion)
    )
    await asyncio.wait_for(completion_staged.wait(), timeout=2)
    persistence = asyncio.create_task(
        _persist_in_new_session(
            auth_sessionmaker,
            job_id=job_id,
            game_id=game_id,
            worker_id="worker-a",
            generation=1,
            score_offset=0,
        )
    )
    await asyncio.sleep(0.1)
    assert not persistence.done()
    release_completion.set()
    assert await asyncio.wait_for(completion, timeout=5) is True
    with pytest.raises(AnalysisRunAuthorityError):
        await asyncio.wait_for(persistence, timeout=5)

    async with auth_sessionmaker() as fresh_session:
        assert (
            await AnalysisResultPersistenceService(fresh_session).read_generation(job_id, 1) is None
        )
