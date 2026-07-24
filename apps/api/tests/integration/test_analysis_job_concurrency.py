import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api import worker as worker_module
from boardtrace_api.analysis.observability import InMemoryAnalysisMetrics
from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.analysis.retry import RetryPolicy, ZeroJitter
from boardtrace_api.config import Settings
from boardtrace_api.models import AnalysisJob, AnalysisJobOutbox
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import (
    AnalysisJobService,
    AnalysisJobTerminalFailureService,
)
from tests.integration.test_analysis_job_orchestration import completed_game
from tests.postgres_helpers import get_test_database_url

pytestmark = [
    pytest.mark.database,
    pytest.mark.integration,
    pytest.mark.queue,
    pytest.mark.concurrency,
]


async def create_job(
    factory: async_sessionmaker[AsyncSession], game_id: UUID, correlation_id: UUID
) -> UUID:
    async with factory() as session:
        job = await AnalysisJobService(session).create_for_completed_game(game_id, correlation_id)
        await session.commit()
        return job.id


async def queue_job(session: AsyncSession, job_id: UUID) -> None:
    repository = AnalysisJobRepository(session)
    event = (await repository.list_publishable_outbox(datetime.now(UTC), 1))[0]
    await repository.mark_outbox_published(event, "message", datetime.now(UTC))
    await session.commit()


@pytest.mark.asyncio
async def test_two_sessions_create_one_job_and_one_outbox(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    game = await completed_game(auth_database_session)
    await auth_database_session.commit()
    first, second = await asyncio.gather(
        create_job(auth_sessionmaker, game.id, uuid4()),
        create_job(auth_sessionmaker, game.id, uuid4()),
    )
    assert first == second
    async with auth_sessionmaker() as session:
        assert await session.scalar(select(func.count(AnalysisJob.id))) == 1
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 1


@pytest.mark.asyncio
async def test_two_workers_claim_only_once(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    await queue_job(auth_database_session, job.id)
    now = datetime.now(UTC)

    async def claim(worker_id: str) -> bool:
        async with auth_sessionmaker() as session:
            claimed = await AnalysisJobRepository(session).claim_job(job.id, worker_id, now, 120)
            await session.commit()
            return claimed is not None

    outcomes = await asyncio.gather(claim("worker-one"), claim("worker-two"))
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.CLAIMED
        assert persisted.attempt_count == 1


@pytest.mark.asyncio
async def test_two_recovery_processes_create_one_retry_event(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    await queue_job(auth_database_session, job.id)
    now = datetime.now(UTC)
    assert await AnalysisJobRepository(auth_database_session).claim_job(job.id, "stale", now, 30)
    await auth_database_session.commit()

    async def recover() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, now + timedelta(seconds=31), RetryPolicy(30, 300, 0), ZeroJitter()
            )
            await session.commit()
            return value is not None

    outcomes = await asyncio.gather(recover(), recover())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.RETRY_SCHEDULED
        assert persisted.attempt_count == 2
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_heartbeat_and_completion_cannot_overwrite_recovery(
    auth_database_session: AsyncSession,
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    await queue_job(auth_database_session, job.id)
    now = datetime.now(UTC)
    repository = AnalysisJobRepository(auth_database_session)
    assert await repository.claim_job(job.id, "worker", now, 30)
    assert await repository.start_job(job.id, "worker", now)
    recovered = await repository.recover_expired_lease(
        job.id, now + timedelta(seconds=31), RetryPolicy(30, 300, 0)
    )
    assert recovered is not None
    assert not await repository.heartbeat_job(job.id, "worker", now + timedelta(seconds=32), 30)
    assert not await repository.complete_job(job.id, "worker", now + timedelta(seconds=32))


@pytest.mark.asyncio
async def test_replacement_lease_generation_rejects_stale_owner_actions(
    auth_database_session: AsyncSession,
) -> None:
    job, baseline = await running_job(auth_database_session, "worker-a")
    repository = AnalysisJobRepository(auth_database_session)
    stale_generation = job.lease_generation
    assert await repository.recover_expired_lease(
        job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
    )
    retry_event = (await repository.list_publishable_outbox(baseline + timedelta(seconds=92), 10))[
        0
    ]
    await repository.mark_outbox_published(retry_event, "replacement-message", baseline)
    replacement = await repository.claim_job(job.id, "worker-a", baseline, 30)
    assert replacement is not None
    assert replacement.lease_generation > stale_generation
    assert not await repository.start_job(job.id, "worker-a", baseline, stale_generation)
    assert await repository.start_job(job.id, "worker-a", baseline, replacement.lease_generation)
    assert not await repository.heartbeat_job(job.id, "worker-a", baseline, 30, stale_generation)
    assert not await repository.complete_job(job.id, "worker-a", baseline, stale_generation)
    assert not await repository.fail_job(
        job.id, "worker-a", "stale", "stale", baseline, stale_generation
    )
    assert await repository.complete_job(job.id, "worker-a", baseline, replacement.lease_generation)


@pytest.mark.asyncio
async def test_concurrent_completion_accepts_one_generation_owner(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def complete() -> bool:
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).complete_job(
                job.id, "worker-a", baseline, generation
            )
            await session.commit()
            return result

    outcomes = await asyncio.gather(complete(), complete())
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1


@pytest.mark.asyncio
async def test_completion_and_terminal_failure_allow_one_terminal_transition(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def complete() -> bool:
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).complete_job(
                job.id, "worker-a", baseline, generation
            )
            await session.commit()
            return result

    async def fail() -> bool:
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).fail_job(
                job.id, "worker-a", "terminal", "terminal", baseline, generation
            )
            await session.commit()
            return result

    outcomes = await asyncio.gather(complete(), fail())
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1


@pytest.mark.asyncio
async def test_concurrent_retryable_failures_create_one_retry_outbox(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def retry() -> bool:
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).schedule_retry(
                job.id,
                "worker-a",
                "temporary",
                "temporary",
                baseline + timedelta(seconds=30),
                uuid4(),
                generation,
            )
            await session.commit()
            return result

    outcomes = await asyncio.gather(retry(), retry())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_worker_retryable_exception_schedules_durable_retry(
    auth_database_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = await completed_game(auth_database_session)
    job = await AnalysisJobService(auth_database_session).create_for_completed_game(
        game.id, uuid4()
    )
    await queue_job(auth_database_session, job.id)
    monkeypatch.setattr(
        worker_module,
        "settings",
        Settings(database_url=PostgresDsn(get_test_database_url())),
    )

    def raise_retryable_error() -> None:
        raise ConnectionError("test failure")

    monkeypatch.setattr(worker_module, "_wait_for_test_gate", raise_retryable_error)
    result = await worker_module._run_analysis(
        AnalysisTaskPayload(schema_version=1, job_id=job.id, correlation_id=uuid4()), "worker-a"
    )
    assert result == "retry_scheduled"
    await auth_database_session.refresh(job)
    assert job.status == AnalysisJobStatus.RETRY_SCHEDULED
    assert job.worker_id is None
    assert await auth_database_session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_retry_outbox_insert_failure_rolls_back_job_transition(
    auth_database_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation
    repository = AnalysisJobRepository(auth_database_session)

    async def fail_outbox(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected retry outbox failure")

    monkeypatch.setattr(repository, "create_retry_outbox_if_absent", fail_outbox)
    with pytest.raises(RuntimeError, match="injected retry outbox failure"):
        await repository.schedule_retry(
            job.id,
            "worker-a",
            "temporary",
            "temporary",
            baseline + timedelta(seconds=30),
            uuid4(),
            generation,
        )
    await auth_database_session.rollback()
    await auth_database_session.refresh(job)
    assert job.status == AnalysisJobStatus.RUNNING
    assert job.worker_id == "worker-a"
    assert await auth_database_session.scalar(select(func.count(AnalysisJobOutbox.id))) == 1


@pytest.mark.asyncio
async def test_completion_and_retryable_failure_allow_one_transition(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def complete() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).complete_job(
                job.id, "worker-a", baseline, generation
            )
            await session.commit()
            return value

    async def retry() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).schedule_retry(
                job.id,
                "worker-a",
                "temporary",
                "temporary",
                baseline + timedelta(seconds=30),
                uuid4(),
                generation,
            )
            await session.commit()
            return value

    outcomes = await asyncio.gather(complete(), retry())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status in {AnalysisJobStatus.SUCCEEDED, AnalysisJobStatus.RETRY_SCHEDULED}
        expected_outbox_count = 1 if persisted.status == AnalysisJobStatus.SUCCEEDED else 2
        assert (
            await session.scalar(select(func.count(AnalysisJobOutbox.id))) == expected_outbox_count
        )


@pytest.mark.asyncio
async def test_recovery_and_stale_retryable_failure_create_one_retry_outbox(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def recover() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return value is not None

    async def retry() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).schedule_retry(
                job.id,
                "worker-a",
                "temporary",
                "temporary",
                baseline + timedelta(seconds=30),
                uuid4(),
                generation,
            )
            await session.commit()
            return value

    outcomes = await asyncio.gather(recover(), retry())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_concurrent_terminal_failures_accept_one_generation_owner(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def fail() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).fail_job(
                job.id, "worker-a", "terminal", "terminal", baseline, generation
            )
            await session.commit()
            return value

    outcomes = await asyncio.gather(fail(), fail())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None and persisted.status == AnalysisJobStatus.FAILED


@pytest.mark.asyncio
async def test_recovery_rejects_stale_terminal_failure(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation

    async def recover() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return value is not None

    async def stale_fail() -> bool:
        async with auth_sessionmaker() as session:
            value = await AnalysisJobRepository(session).fail_job(
                job.id, "worker-a", "terminal", "terminal", baseline, generation
            )
            await session.commit()
            return value

    outcomes = await asyncio.gather(recover(), stale_fail())
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status in {AnalysisJobStatus.FAILED, AnalysisJobStatus.RETRY_SCHEDULED}


@pytest.mark.asyncio
async def test_terminal_failure_before_commit_error_rolls_back_without_success_observability(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, baseline = await running_job(auth_database_session)
    job_id = job.id
    generation = job.lease_generation
    metrics = InMemoryAnalysisMetrics()
    audit_records: list[tuple[str, dict[str, object]]] = []

    def record_audit(event: str, **context: object) -> None:
        audit_records.append((event, context))

    async def fail_before_commit() -> None:
        raise RuntimeError("controlled terminal persistence failure")

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", record_audit)
    with pytest.raises(RuntimeError, match="controlled terminal persistence failure"):
        await AnalysisJobTerminalFailureService(auth_database_session, metrics).fail_job(
            job_id,
            "worker-a",
            "terminal",
            "terminal failure",
            baseline,
            generation,
            fail_before_commit,
        )

    async with auth_sessionmaker() as verification_session:
        persisted = await AnalysisJobRepository(verification_session).get_by_id(job_id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.RUNNING
        assert persisted.worker_id == "worker-a"
        assert persisted.lease_generation == generation
        assert persisted.last_error_code is None
    assert not metrics.counters
    assert audit_records == []


@pytest.mark.asyncio
async def test_concurrent_terminal_failures_emit_one_success_and_one_rejection_observation(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation
    metrics = InMemoryAnalysisMetrics()
    audit_records: list[tuple[str, dict[str, object]]] = []

    def record_audit(event: str, **context: object) -> None:
        audit_records.append((event, context))

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", record_audit)

    async def fail() -> bool:
        async with auth_sessionmaker() as session:
            return await AnalysisJobTerminalFailureService(session, metrics).fail_job(
                job.id, "worker-a", "terminal", "terminal failure", baseline, generation
            )

    outcomes = await asyncio.gather(fail(), fail())
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert metrics.counters[("analysis_jobs_failed_total", "FAILED", "terminal")] == 1
    assert (
        metrics.counters[
            ("analysis_job_invalid_transitions_total", None, "terminal_failure_rejected")
        ]
        == 1
    )
    assert [event for event, _ in audit_records].count("analysis_job_failed") == 1
    assert [event for event, _ in audit_records].count(
        "analysis_job_invalid_transition_rejected"
    ) == 1
    async with auth_sessionmaker() as verification_session:
        persisted = await AnalysisJobRepository(verification_session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.FAILED


@pytest.mark.asyncio
async def test_recovery_and_stale_terminal_failure_emit_at_most_one_success_signal(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, baseline = await running_job(auth_database_session)
    generation = job.lease_generation
    metrics = InMemoryAnalysisMetrics()
    audit_records: list[tuple[str, dict[str, object]]] = []

    def record_audit(event: str, **context: object) -> None:
        audit_records.append((event, context))

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", record_audit)

    async def recover() -> bool:
        async with auth_sessionmaker() as session:
            recovered = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return recovered is not None

    async def stale_fail() -> bool:
        async with auth_sessionmaker() as session:
            return await AnalysisJobTerminalFailureService(session, metrics).fail_job(
                job.id, "worker-a", "terminal", "terminal failure", baseline, generation
            )

    outcomes = await asyncio.gather(recover(), stale_fail())
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert metrics.counters[("analysis_jobs_failed_total", "FAILED", "terminal")] <= 1
    assert [event for event, _ in audit_records].count("analysis_job_failed") <= 1
    if outcomes[1]:
        assert metrics.counters[("analysis_jobs_failed_total", "FAILED", "terminal")] == 1
        assert not [
            event
            for event, _ in audit_records
            if event == "analysis_job_invalid_transition_rejected"
        ]
    else:
        assert (
            metrics.counters[
                ("analysis_job_invalid_transitions_total", None, "terminal_failure_rejected")
            ]
            == 1
        )
    async with auth_sessionmaker() as verification_session:
        persisted = await AnalysisJobRepository(verification_session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status in {AnalysisJobStatus.FAILED, AnalysisJobStatus.RETRY_SCHEDULED}


@pytest.mark.asyncio
async def test_publishers_skip_locked_rows(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    game = await completed_game(auth_database_session)
    await AnalysisJobService(auth_database_session).create_for_completed_game(game.id, uuid4())
    now = datetime.now(UTC)
    first = AnalysisJobRepository(auth_database_session)
    locked = await first.list_publishable_outbox(now, 10)
    assert len(locked) == 1
    # A second transaction observes no locked row because PostgreSQL skips this lock.
    async with auth_sessionmaker() as second_session:
        second = await AnalysisJobRepository(second_session).list_publishable_outbox(now, 10)
        assert second == []
    await auth_database_session.rollback()


async def running_job(
    session: AsyncSession, worker_id: str = "worker-a"
) -> tuple[AnalysisJob, datetime]:
    game = await completed_game(session)
    job = await AnalysisJobService(session).create_for_completed_game(game.id, uuid4())
    await queue_job(session, job.id)
    baseline = datetime.now(UTC)
    repository = AnalysisJobRepository(session)
    assert await repository.claim_job(job.id, worker_id, baseline, 30)
    assert await repository.start_job(job.id, worker_id, baseline)
    await session.commit()
    return job, baseline


@pytest.mark.asyncio
async def test_heartbeat_first_blocks_recovery_then_preserves_running_lease(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    locked = asyncio.Event()
    release = asyncio.Event()

    async def heartbeat() -> bool:
        async with auth_sessionmaker() as session:
            repository = AnalysisJobRepository(session)
            assert await repository.get_by_id(job.id, lock=True)
            locked.set()
            await asyncio.wait_for(release.wait(), 3)
            result = await repository.heartbeat_job(
                job.id, "worker-a", baseline + timedelta(seconds=29), 60
            )
            await session.commit()
            return result

    async def recovery() -> bool:
        await asyncio.wait_for(locked.wait(), 3)
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return result is not None

    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.wait_for(locked.wait(), 3)
    recovery_task = asyncio.create_task(recovery())
    release.set()
    assert await asyncio.wait_for(heartbeat_task, 3)
    assert not await asyncio.wait_for(recovery_task, 3)
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.RUNNING
        assert persisted.worker_id == "worker-a"
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 1


@pytest.mark.asyncio
async def test_recovery_first_blocks_stale_heartbeat_and_completion(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    locked = asyncio.Event()
    release = asyncio.Event()

    async def recovery() -> bool:
        async with auth_sessionmaker() as session:
            repository = AnalysisJobRepository(session)
            assert await repository.get_by_id(job.id, lock=True)
            locked.set()
            await asyncio.wait_for(release.wait(), 3)
            result = await repository.recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return result is not None

    async def stale_actions() -> tuple[bool, bool]:
        await asyncio.wait_for(locked.wait(), 3)
        async with auth_sessionmaker() as session:
            repository = AnalysisJobRepository(session)
            heartbeat = await repository.heartbeat_job(
                job.id, "worker-a", baseline + timedelta(seconds=32), 30
            )
            completion = await repository.complete_job(
                job.id, "worker-a", baseline + timedelta(seconds=32)
            )
            await session.commit()
            return heartbeat, completion

    recovery_task = asyncio.create_task(recovery())
    await asyncio.wait_for(locked.wait(), 3)
    stale_task = asyncio.create_task(stale_actions())
    release.set()
    assert await asyncio.wait_for(recovery_task, 3)
    assert await asyncio.wait_for(stale_task, 3) == (False, False)
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.RETRY_SCHEDULED
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_completion_first_blocks_recovery_and_keeps_terminal_state(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    locked = asyncio.Event()
    release = asyncio.Event()

    async def complete() -> bool:
        async with auth_sessionmaker() as session:
            repository = AnalysisJobRepository(session)
            assert await repository.get_by_id(job.id, lock=True)
            locked.set()
            await asyncio.wait_for(release.wait(), 3)
            result = await repository.complete_job(
                job.id, "worker-a", baseline + timedelta(seconds=31)
            )
            await session.commit()
            return result

    async def recovery() -> bool:
        await asyncio.wait_for(locked.wait(), 3)
        async with auth_sessionmaker() as session:
            result = await AnalysisJobRepository(session).recover_expired_lease(
                job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
            )
            await session.commit()
            return result is not None

    complete_task = asyncio.create_task(complete())
    await asyncio.wait_for(locked.wait(), 3)
    recovery_task = asyncio.create_task(recovery())
    release.set()
    assert await asyncio.wait_for(complete_task, 3)
    assert not await asyncio.wait_for(recovery_task, 3)
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.SUCCEEDED
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 1


@pytest.mark.asyncio
async def test_retry_scheduled_duplicate_deliveries_claim_and_complete_once(
    auth_database_session: AsyncSession, auth_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job, baseline = await running_job(auth_database_session)
    repository = AnalysisJobRepository(auth_database_session)
    assert await repository.recover_expired_lease(
        job.id, baseline + timedelta(seconds=31), RetryPolicy(30, 300, 0)
    )
    due = baseline + timedelta(seconds=92)
    retry_event = (await repository.list_publishable_outbox(due, 10))[0]
    await repository.mark_outbox_published(retry_event, "retry-message", due)
    await auth_database_session.commit()

    async def delivery(worker_id: str) -> bool:
        async with auth_sessionmaker() as session:
            worker_repository = AnalysisJobRepository(session)
            claimed = await worker_repository.claim_job(job.id, worker_id, due, 30)
            await session.commit()
            if claimed is None:
                return False
        async with auth_sessionmaker() as session:
            worker_repository = AnalysisJobRepository(session)
            assert await worker_repository.start_job(job.id, worker_id, due)
            assert await worker_repository.complete_job(job.id, worker_id, due)
            await session.commit()
            return True

    outcomes = await asyncio.gather(delivery("retry-worker-a"), delivery("retry-worker-b"))
    assert outcomes.count(True) == 1
    async with auth_sessionmaker() as session:
        persisted = await AnalysisJobRepository(session).get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.SUCCEEDED
        assert persisted.attempt_count == 3
        assert await session.scalar(select(func.count(AnalysisJobOutbox.id))) == 2


@pytest.mark.asyncio
async def test_active_lease_duplicate_delivery_emits_only_duplicate_observability(
    auth_database_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, baseline = await running_job(auth_database_session)
    before_worker_id = job.worker_id
    before_lease = job.lease_expires_at
    before_attempts = job.attempt_count
    metrics = InMemoryAnalysisMetrics()
    monkeypatch.setattr(worker_module, "metrics", metrics)

    with caplog.at_level(logging.INFO, logger="boardtrace_api.analysis"):
        result = await worker_module._run_analysis(
            AnalysisTaskPayload(schema_version=1, job_id=job.id, correlation_id=uuid4()), "worker-b"
        )

    assert result == "duplicate_or_ineligible"
    await auth_database_session.refresh(job)
    assert job.status == AnalysisJobStatus.RUNNING
    assert job.worker_id == before_worker_id
    assert job.lease_expires_at == before_lease
    assert job.attempt_count == before_attempts
    assert metrics.counters[("analysis_job_duplicate_deliveries_total", None, None)] == 1
    assert metrics.counters[("analysis_jobs_claimed_total", None, None)] == 0
    assert metrics.counters[("analysis_jobs_started_total", None, None)] == 0
    assert metrics.counters[("analysis_jobs_succeeded_total", None, None)] == 0
    assert all(name != "analysis_job_duration_seconds" for name, _ in metrics.observations)
    assert [
        record.message
        for record in caplog.records
        if record.message == "analysis_job_duplicate_delivery_ignored"
    ] == ["analysis_job_duplicate_delivery_ignored"]
