"""Opt-in real Stockfish execution through the Prompt 10-D worker lifecycle."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api import worker as worker_module
from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.config import Settings
from boardtrace_api.models import AnalysisJob, AnalysisRun, Game
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import AnalysisJobService
from tests.integration.test_analysis_job_orchestration import completed_game
from tests.postgres_helpers import get_test_database_url

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.runtime]


def _stockfish_path() -> str:
    configured = os.environ.get("BOARDTRACE_TEST_STOCKFISH_PATH")
    if configured is None or not Path(configured).is_file():
        pytest.skip("BOARDTRACE_TEST_STOCKFISH_PATH does not name a Stockfish executable")
    return configured


@pytest.mark.asyncio
async def test_worker_real_stockfish_persists_then_completes_without_release(
    auth_database_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    repository = AnalysisJobRepository(auth_database_session)
    event = (await repository.list_publishable_outbox(datetime.now(UTC), 1))[0]
    await repository.mark_outbox_published(event, "runtime-message", datetime.now(UTC))
    await auth_database_session.commit()
    job_id = job.id
    game_id = game.id

    monkeypatch.setattr(
        worker_module,
        "settings",
        Settings(
            database_url=PostgresDsn(get_test_database_url()),
            stockfish_path=_stockfish_path(),
            analysis_depth=4,
            analysis_max_position_time_ms=100,
            analysis_max_game_time_ms=5_000,
            analysis_max_moves=10,
            analysis_max_positions=11,
        ),
    )

    outcome = await worker_module._run_analysis(
        AnalysisTaskPayload(schema_version=1, job_id=job_id, correlation_id=uuid4()),
        "stockfish-worker-10-d",
    )

    auth_database_session.expire_all()
    persisted_job = await auth_database_session.get(AnalysisJob, job_id)
    persisted_game = await auth_database_session.get(Game, game_id)
    assert outcome == "completed"
    assert persisted_job is not None and persisted_job.status is AnalysisJobStatus.SUCCEEDED
    assert persisted_game is not None and persisted_game.analysis_available_at is None
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1
