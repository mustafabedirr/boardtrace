from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.retry import RetryPolicy
from boardtrace_api.models import AnalysisJob, AnalysisJobOutbox, Game, User
from boardtrace_api.models.enums import (
    AnalysisJobStatus,
    GameResult,
    GameStatus,
    PlayerColor,
)
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import AnalysisJobService, OutboxPublisher

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.queue]


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    def enqueue_analysis_job(self, job_id: UUID, correlation_id: UUID) -> str:
        self.calls.append((job_id, correlation_id))
        return "test-message-id"


class UnavailableQueue:
    def enqueue_analysis_job(self, job_id: UUID, correlation_id: UUID) -> str:
        raise ConnectionError("temporary test broker outage")


async def completed_game(session: AsyncSession) -> Game:
    user = User(
        email=f"analysis-{uuid4()}@example.com",
        normalized_email=f"analysis-{uuid4()}@example.com",
        display_name=None,
        password_hash=None,
    )
    session.add(user)
    await session.flush()
    game = Game(
        user_id=user.id,
        status=GameStatus.FINISHED,
        platform="lichess",
        player_color=PlayerColor.UNKNOWN,
        result=GameResult.UNKNOWN,
        finished_at=datetime.now(UTC),
        completion_verified_at=datetime.now(UTC),
        source_game_id=str(uuid4()),
        ingestion_key=uuid4().hex + uuid4().hex,
        ingestion_payload_hash=uuid4().hex + uuid4().hex,
        normalized_moves=["e2e4"],
    )
    session.add(game)
    await session.flush()
    return game


@pytest.mark.asyncio
async def test_job_outbox_publish_claim_and_noop_completion_foundation(
    auth_database_session: AsyncSession,
) -> None:
    game = await completed_game(auth_database_session)
    service = AnalysisJobService(auth_database_session)
    job = await service.create_for_completed_game(game.id, uuid4())
    duplicate = await service.create_for_completed_game(game.id, uuid4())
    assert duplicate.id == job.id
    assert await auth_database_session.scalar(select(func.count(AnalysisJob.id))) == 1
    assert await auth_database_session.scalar(select(func.count(AnalysisJobOutbox.id))) == 1

    queue = FakeQueue()
    now = datetime.now(UTC)
    assert await OutboxPublisher(auth_database_session, queue).publish_due(now) == 1
    assert len(queue.calls) == 1
    repository = AnalysisJobRepository(auth_database_session)
    claimed = await repository.claim_job(job.id, "worker-a", now, 120)
    assert claimed is not None
    assert not await repository.heartbeat_job(job.id, "worker-b", now, 120)
    assert await repository.start_job(job.id, "worker-a", now)
    assert await repository.complete_job(job.id, "worker-a", now)
    assert not await repository.claim_job(job.id, "worker-b", now, 120)
    await auth_database_session.commit()
    await auth_database_session.refresh(job)
    assert job.status == AnalysisJobStatus.SUCCEEDED
    assert game.analysis_available_at is None


@pytest.mark.asyncio
async def test_expired_lease_recovery_is_state_based(
    auth_database_session: AsyncSession,
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    repository = AnalysisJobRepository(auth_database_session)
    event = (await repository.list_publishable_outbox(datetime.now(UTC), 1))[0]
    await repository.mark_outbox_published(event, "message", datetime.now(UTC))
    now = datetime.now(UTC)
    assert await repository.claim_job(job.id, "stale-worker", now, 30) is not None
    recovered = await repository.recover_expired_lease(
        job.id, now + timedelta(seconds=31), RetryPolicy(30, 300, 0)
    )
    assert recovered is not None
    assert recovered.status == AnalysisJobStatus.RETRY_SCHEDULED
    assert recovered.worker_id is None
    assert recovered.attempt_count == 2
    assert await auth_database_session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_outbox_publish_failure_keeps_event_pending_with_retry_delay(
    auth_database_session: AsyncSession,
) -> None:
    game = await completed_game(auth_database_session)
    await AnalysisJobService(auth_database_session).create_for_completed_game(game.id, uuid4())
    now = datetime.now(UTC)
    assert await OutboxPublisher(auth_database_session, UnavailableQueue()).publish_due(now) == 0
    event = await AnalysisJobRepository(auth_database_session).list_publishable_outbox(now, 1)
    assert event == []
    pending = await auth_database_session.scalar(select(AnalysisJobOutbox))
    assert pending is not None
    assert pending.last_error_code == "queue_temporarily_unavailable"
    assert pending.attempt_count == 1
    assert pending.next_attempt_at is not None
    assert pending.next_attempt_at > now
