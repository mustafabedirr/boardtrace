"""Prompt 10-D-2 distributed runtime closure with real external processes."""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.queue import ANALYSIS_TASK, AnalysisTaskPayload
from boardtrace_api.analysis.retry import RetryPolicy
from boardtrace_api.models import AnalysisJob, AnalysisJobOutbox, AnalysisRun
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import AnalysisJobService
from tests.integration.test_analysis_job_orchestration import completed_game
from tests.postgres_helpers import get_test_database_url
from tests.runtime.celery_harness import RuntimeCeleryHarness
from tests.runtime.controllers import CeleryWorkerController, RedisContainerController
from tests.runtime.test_auth_uvicorn_smoke import unused_port

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.queue, pytest.mark.runtime]


def _stockfish_path() -> str:
    configured = os.environ.get("BOARDTRACE_TEST_STOCKFISH_PATH")
    if configured is None or not Path(configured).is_file():
        pytest.skip("BOARDTRACE_TEST_STOCKFISH_PATH does not name a Stockfish executable")
    return configured


async def _wait_status(
    session: AsyncSession,
    job_id: UUID,
    expected: set[AnalysisJobStatus],
    timeout: float = 20,
) -> AnalysisJob:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.expire_all()
        job = await AnalysisJobRepository(session).get_by_id(job_id)
        if job is not None and job.status in expected:
            return job
        await asyncio.sleep(0.1)
    pytest.fail(f"analysis job did not reach {sorted(item.value for item in expected)}")


async def _queued_job(session: AsyncSession) -> tuple[UUID, UUID]:
    game = await completed_game(session)
    correlation_id = uuid4()
    job = await AnalysisJobService(session).create_for_completed_game(game.id, correlation_id)
    job_id = job.id
    await session.commit()
    return job_id, correlation_id


def _worker(
    database_url: str,
    broker_url: str,
    harness: RuntimeCeleryHarness,
    stockfish_path: str,
    **environment: str,
) -> CeleryWorkerController:
    return CeleryWorkerController(
        database_url,
        {
            "BOARDTRACE_REDIS_URL": broker_url,
            "BOARDTRACE_STOCKFISH_PATH": stockfish_path,
            "BOARDTRACE_ANALYSIS_DEPTH": "4",
            "BOARDTRACE_ANALYSIS_MAX_POSITION_TIME_MS": "100",
            "BOARDTRACE_ANALYSIS_MAX_GAME_TIME_MS": "5000",
            "BOARDTRACE_ANALYSIS_MAX_MOVES": "10",
            "BOARDTRACE_ANALYSIS_MAX_POSITIONS": "11",
        }
        | environment,
        harness.app,
    )


@pytest.mark.asyncio
async def test_retry_stale_delivery_eventual_success_and_commit_redelivery(
    auth_database_session: AsyncSession,
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-10d2-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    failing = _worker(database_url, broker_url, harness, "missing-stockfish-10d2")
    succeeding: CeleryWorkerController | None = None
    try:
        redis.start()
        failing.start()
        job_id, correlation_id = await _queued_job(auth_database_session)
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        retry = await _wait_status(
            auth_database_session, job_id, {AnalysisJobStatus.RETRY_SCHEDULED}
        )
        first_generation = retry.lease_generation
        assert retry.last_error_code == "engine_execution_failed"
        assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0
        failing.graceful_stop()

        harness.app.send_task(
            ANALYSIS_TASK,
            kwargs={
                "payload": AnalysisTaskPayload(
                    schema_version=1, job_id=job_id, correlation_id=correlation_id
                ).model_dump(mode="json")
            },
        )
        succeeding = _worker(database_url, broker_url, harness, _stockfish_path())
        succeeding.start()
        await asyncio.sleep(0.5)
        stale = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
        assert stale is not None and stale.status is AnalysisJobStatus.RETRY_SCHEDULED
        assert stale.lease_generation == first_generation

        retry_outbox = (
            await auth_database_session.scalars(
                select(AnalysisJobOutbox)
                .where(AnalysisJobOutbox.analysis_job_id == job_id)
                .order_by(AnalysisJobOutbox.delivery_generation.desc())
            )
        ).first()
        assert retry_outbox is not None
        retry_outbox.next_attempt_at = datetime.now(UTC)
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        completed = await _wait_status(auth_database_session, job_id, {AnalysisJobStatus.SUCCEEDED})
        assert completed.lease_generation > first_generation
        assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1

        harness.app.send_task(
            ANALYSIS_TASK,
            kwargs={
                "payload": AnalysisTaskPayload(
                    schema_version=1, job_id=job_id, correlation_id=correlation_id
                ).model_dump(mode="json")
            },
        )
        await asyncio.sleep(0.75)
        duplicate = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
        assert duplicate is not None and duplicate.status is AnalysisJobStatus.SUCCEEDED
        assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1
    finally:
        failing.graceful_stop()
        if succeeding is not None:
            succeeding.graceful_stop()
        harness.close()
        redis.remove()


@pytest.mark.asyncio
async def test_permanent_invalid_game_failure_is_terminal_and_non_durable(
    auth_database_session: AsyncSession,
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-10d2-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    worker = _worker(database_url, broker_url, harness, _stockfish_path())
    try:
        redis.start()
        worker.start()
        game = await completed_game(auth_database_session)
        job = await AnalysisJobService(auth_database_session).create_for_completed_game(
            game.id, uuid4()
        )
        job_id = job.id
        game.normalized_moves = []
        await auth_database_session.commit()
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        failed = await _wait_status(auth_database_session, job_id, {AnalysisJobStatus.FAILED})
        assert failed.last_error_code == "invalid_job_request"
        assert failed.worker_id is None
        assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 0
        outbox_count = await auth_database_session.scalar(
            select(func.count(AnalysisJobOutbox.id)).where(
                AnalysisJobOutbox.analysis_job_id == job_id
            )
        )
        assert outbox_count == 1
    finally:
        worker.graceful_stop()
        harness.close()
        redis.remove()


def _stockfish_process_ids() -> set[int]:
    if os.name == "nt":
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-Process | Where-Object {$_.ProcessName -like 'stockfish*'} "
                "| ForEach-Object {$_.Id}",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    else:
        result = subprocess.run(
            ["pgrep", "-f", "stockfish"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    return {int(value) for value in result.stdout.split() if value.isdigit()}


def _terminate_processes(process_ids: set[int]) -> None:
    for process_id in process_ids:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            subprocess.run(
                ["kill", "-KILL", str(process_id)],
                capture_output=True,
                check=False,
                timeout=10,
            )


@pytest.mark.asyncio
async def test_worker_loss_during_stockfish_recovers_with_replacement_generation(
    auth_database_session: AsyncSession,
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-10d2-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    slow = _worker(
        database_url,
        broker_url,
        harness,
        _stockfish_path(),
        BOARDTRACE_ANALYSIS_DEPTH="99",
        BOARDTRACE_ANALYSIS_MAX_POSITION_TIME_MS="30000",
        BOARDTRACE_ANALYSIS_MAX_GAME_TIME_MS="60000",
    )
    replacement: CeleryWorkerController | None = None
    orphaned: set[int] = set()
    try:
        redis.start()
        slow.start()
        job_id, _ = await _queued_job(auth_database_session)
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        running = await _wait_status(auth_database_session, job_id, {AnalysisJobStatus.RUNNING})
        first_generation = running.lease_generation
        deadline = time.monotonic() + 10
        active: set[int] = set()
        while time.monotonic() < deadline:
            active = _stockfish_process_ids()
            if active:
                break
            await asyncio.sleep(0.1)
        assert active, "real Stockfish subprocess was not observed"
        slow.kill()
        orphaned = _stockfish_process_ids()
        _terminate_processes(orphaned)
        orphaned.clear()

        recovered = await AnalysisJobRepository(auth_database_session).recover_expired_lease(
            job_id, datetime.now(UTC) + timedelta(seconds=121), RetryPolicy(1, 1, 0)
        )
        assert recovered is not None
        assert recovered.status is AnalysisJobStatus.RETRY_SCHEDULED
        assert recovered.lease_generation == first_generation
        await auth_database_session.commit()
        retry_outbox = (
            await auth_database_session.scalars(
                select(AnalysisJobOutbox)
                .where(AnalysisJobOutbox.analysis_job_id == job_id)
                .order_by(AnalysisJobOutbox.delivery_generation.desc())
            )
        ).first()
        assert retry_outbox is not None
        retry_outbox.next_attempt_at = datetime.now(UTC)
        replacement = _worker(database_url, broker_url, harness, _stockfish_path())
        replacement.start()
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        completed = await _wait_status(auth_database_session, job_id, {AnalysisJobStatus.SUCCEEDED})
        assert completed.lease_generation > first_generation
        assert await auth_database_session.scalar(select(func.count(AnalysisRun.id))) == 1
    finally:
        slow.graceful_stop()
        if replacement is not None:
            replacement.graceful_stop()
        _terminate_processes(orphaned | _stockfish_process_ids())
        harness.close()
        redis.remove()
