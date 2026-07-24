from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api import worker as worker_module
from boardtrace_api.analysis.full_game import CompletedGameAnalysisInput, FullGameAnalysisBudget
from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.config import Settings
from boardtrace_api.models import AnalysisJob, AnalysisRun, Game
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import AnalysisJobService
from tests.integration.test_analysis_job_orchestration import completed_game
from tests.integration.test_analysis_result_persistence import _result
from tests.postgres_helpers import get_test_database_url

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.queue]


class RecordingAnalyzer:
    games: list[CompletedGameAnalysisInput] = []
    budgets: list[FullGameAnalysisBudget] = []

    def __init__(self, _engine: object) -> None:
        pass

    def analyse(self, game: CompletedGameAnalysisInput, budget: FullGameAnalysisBudget) -> object:
        self.games.append(game)
        self.budgets.append(budget)
        return _result(game.game_id)


@pytest.mark.asyncio
async def test_worker_runs_server_game_then_atomically_persists_and_completes(
    auth_database_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordingAnalyzer.games.clear()
    RecordingAnalyzer.budgets.clear()
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    repository = AnalysisJobRepository(auth_database_session)
    event = (await repository.list_publishable_outbox(datetime.now(UTC), 1))[0]
    await repository.mark_outbox_published(event, "message", datetime.now(UTC))
    await auth_database_session.commit()
    job_id = job.id
    game_id = game.id
    expected_moves = tuple(game.normalized_moves or ())
    expected_completion = game.completion_verified_at

    monkeypatch.setattr(
        worker_module,
        "settings",
        Settings(database_url=PostgresDsn(get_test_database_url()), stockfish_path="stockfish"),
    )
    monkeypatch.setattr(worker_module, "FullGameAnalyzer", RecordingAnalyzer)

    outcome = await worker_module._run_analysis(
        AnalysisTaskPayload(schema_version=1, job_id=job_id, correlation_id=uuid4()),
        "worker-10-d",
    )

    assert outcome == "completed"
    auth_database_session.expire_all()
    persisted_job = await auth_database_session.get(AnalysisJob, job_id)
    persisted_game = await auth_database_session.get(Game, game_id)
    assert persisted_job is not None and persisted_job.status is AnalysisJobStatus.SUCCEEDED
    assert persisted_job.worker_id is None
    assert persisted_game is not None and persisted_game.analysis_available_at is None
    assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1
    assert len(RecordingAnalyzer.games) == 1
    assert RecordingAnalyzer.games[0].normalized_moves_uci == expected_moves
    assert RecordingAnalyzer.games[0].completion_verified_at == expected_completion
    assert len(RecordingAnalyzer.budgets) == 1
