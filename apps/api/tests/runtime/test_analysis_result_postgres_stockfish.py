"""Opt-in end-to-end internal result persistence with native Stockfish and PostgreSQL."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.analysis.full_game import (
    CompletedGameAnalysisInput,
    EngineReusePolicy,
    FullGameAnalysisBudget,
    FullGameAnalyzer,
)
from boardtrace_api.analysis.stockfish import StockfishEngine
from boardtrace_api.models import AnalysisJob, Game, User
from boardtrace_api.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
    GameResult,
    GameStatus,
    PlayerColor,
)
from boardtrace_api.services.analysis_results import (
    AnalysisResultPersistenceService,
    EngineConfigurationSnapshot,
)
from tests.integration.test_analysis_result_persistence import _assert_minimized_read_back

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.runtime]


def _stockfish_path() -> str:
    configured = os.environ.get("BOARDTRACE_TEST_STOCKFISH_PATH")
    if configured is None or not Path(configured).is_file():
        pytest.skip("BOARDTRACE_TEST_STOCKFISH_PATH does not name a native Stockfish executable")
    return configured


@pytest.mark.asyncio
async def test_real_stockfish_full_game_persists_and_typed_reads_from_fresh_session(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = User(
        email=f"stockfish-persistence-{uuid4()}@example.test",
        normalized_email=f"stockfish-persistence-{uuid4()}@example.test",
        display_name=None,
        password_hash=None,
    )
    auth_database_session.add(user)
    await auth_database_session.flush()
    moves = ("e2e4", "e7e5", "g1f3")
    game = Game(
        user_id=user.id,
        status=GameStatus.FINISHED,
        platform="runtime-test",
        player_color=PlayerColor.UNKNOWN,
        result=GameResult.UNKNOWN,
        completion_verified_at=datetime.now(UTC),
        normalized_moves=list(moves),
        source_game_id=str(uuid4()),
    )
    auth_database_session.add(game)
    await auth_database_session.flush()
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
        lease_generation=1,
        worker_id="stockfish-runtime-worker",
    )
    auth_database_session.add(job)
    await auth_database_session.commit()

    budget = FullGameAnalysisBudget(
        depth=4,
        max_position_time_ms=1_000,
        max_moves=3,
        max_positions=4,
        max_game_time_ms=5_000,
    )
    result = FullGameAnalyzer(
        StockfishEngine(_stockfish_path(), threads=1, hash_mb=16, timeout_seconds=5)
    ).analyse(
        CompletedGameAnalysisInput(
            game_id=game.id,
            game_status=game.status,
            completion_verified_at=game.completion_verified_at,
            initial_fen=None,
            normalized_moves_uci=moves,
        ),
        budget,
    )
    configuration = EngineConfigurationSnapshot(
        schema_version=1,
        depth=budget.depth,
        max_position_time_ms=budget.max_position_time_ms,
        max_game_time_ms=budget.max_game_time_ms,
        max_positions=budget.max_positions,
        max_moves=budget.max_moves,
        threads=1,
        hash_mb=16,
        command_timeout_ms=5_000,
        reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
    )
    started_at = datetime.now(UTC)
    run = await AnalysisResultPersistenceService(auth_database_session).persist_owned_generation(
        job_id=job.id,
        worker_id="stockfish-runtime-worker",
        lease_generation=1,
        result=result,
        configuration=configuration,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )

    async with auth_sessionmaker() as fresh_session:
        read_back = await AnalysisResultPersistenceService(fresh_session).read_generation(job.id, 1)
        assert read_back is not None
        assert read_back.run_id == run.id
        _assert_minimized_read_back(read_back.result, result)
        assert read_back.configuration == configuration
        assert len(read_back.result.position_evaluations) == 4
        assert len(read_back.result.move_evaluations) == 3
