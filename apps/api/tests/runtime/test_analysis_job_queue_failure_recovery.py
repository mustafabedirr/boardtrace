import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.queue import ANALYSIS_TASK, OUTBOX_PUBLISH_TASK, AnalysisTaskPayload
from boardtrace_api.analysis.retry import RetryPolicy
from boardtrace_api.models import AnalysisJobOutbox
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import AnalysisJobService
from tests.integration.test_analysis_job_orchestration import completed_game
from tests.postgres_helpers import get_test_database_url
from tests.runtime.celery_harness import RuntimeCeleryHarness
from tests.runtime.controllers import CeleryWorkerController, RedisContainerController
from tests.runtime.test_analysis_job_queue_uvicorn import wait_for_job_status
from tests.runtime.test_auth_uvicorn_smoke import (
    AUTH_PREFIX,
    PASSWORD,
    assert_no_store,
    unused_port,
    uvicorn_process,
    wait_for_ready,
)

pytestmark = [
    pytest.mark.database,
    pytest.mark.integration,
    pytest.mark.queue,
    pytest.mark.runtime,
]


def test_worker_unavailable_message_persists_then_completes(
    auth_database_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-runtime-{uuid4().hex}", broker_port)
    monkeypatch.setenv("BOARDTRACE_REDIS_URL", broker_url)
    harness = RuntimeCeleryHarness.create(broker_url)
    try:
        redis.start()
        with (
            uvicorn_process(database_url) as (server, base_url),
            httpx.Client(timeout=5) as client,
        ):
            wait_for_ready(client, base_url, server)
            owner = client.post(
                f"{base_url}{AUTH_PREFIX}/register",
                json={"email": "runtime-no-worker@example.com", "password": PASSWORD},
            )
            assert owner.status_code == 200
            assert_no_store(owner)
            web_token = owner.json()["access_token"]
            pairing = client.post(
                f"{base_url}/api/v1/extension-pairings",
                headers={"Authorization": f"Bearer {web_token}"},
                json={"extension_id": "runtime-no-worker", "scopes": ["games:ingest"]},
            )
            extension = client.post(
                f"{base_url}/api/v1/extension-pairings/exchange",
                json={"code": pairing.json()["code"], "extension_id": "runtime-no-worker"},
            )
            payload = {
                "idempotency_key": hashlib.sha256(b"runtime-no-worker").hexdigest(),
                "platform": "lichess",
                "source_game_id": "RuntimeNoWorker",
                "completed_at": "2026-07-18T10:00:00Z",
                "player_color": "UNKNOWN",
                "result": "UNKNOWN",
                "initial_fen": None,
                "moves": ["e2e4"],
            }
            ingestion = client.post(
                f"{base_url}/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {extension.json()['access_token']}"},
                json=payload,
            )
            assert ingestion.status_code == 201
            job_id = ingestion.json()["analysis_job_id"]
            harness.app.send_task(OUTBOX_PUBLISH_TASK)
            pending = client.get(
                f"{base_url}/api/v1/analysis/jobs/{job_id}",
                headers={"Authorization": f"Bearer {web_token}"},
            )
            assert pending.status_code == 200
            assert pending.json()["status"] in {"PENDING", "QUEUED"}
            assert pending.json()["analysis_available"] is False
            assert (
                client.post(
                    f"{base_url}/api/v1/games/ingestions",
                    headers={"Authorization": f"Bearer {extension.json()['access_token']}"},
                    json=payload,
                ).json()["analysis_job_id"]
                == job_id
            )
            worker = CeleryWorkerController(
                database_url, {"BOARDTRACE_REDIS_URL": broker_url}, harness.app
            )
            try:
                worker.start()
                status = wait_for_job_status(client, base_url, web_token, job_id)
                assert status["analysis_available"] is False
                assert worker.process is not None and worker.process.poll() is None
            finally:
                worker.graceful_stop()
                worker.assert_not_running()
            assert server.poll() is None
        server.communicate(timeout=1)
    finally:
        harness.close()
        redis.remove()


@pytest.mark.asyncio
async def test_redis_outage_persists_publish_retry_and_completes_after_restart(
    auth_database_session: AsyncSession,
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-runtime-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    worker = CeleryWorkerController(database_url, {"BOARDTRACE_REDIS_URL": broker_url}, harness.app)
    try:
        redis.start()
        game = await completed_game(auth_database_session)
        job = await AnalysisJobService(auth_database_session).create_for_completed_game(
            game.id, uuid4()
        )
        await auth_database_session.commit()
        redis.stop()
        assert redis.inspect_state() == "exited"
        publisher = harness.publisher(auth_database_session)
        assert await publisher.publish_due(datetime.now(UTC)) == 0
        await auth_database_session.commit()
        event = await AnalysisJobRepository(auth_database_session).list_publishable_outbox(
            datetime.now(UTC), 1
        )
        assert event == []
        persisted = await AnalysisJobRepository(auth_database_session).get_by_id(job.id)
        assert persisted is not None and persisted.status != AnalysisJobStatus.SUCCEEDED
        redis.restart()
        harness.close()
        harness = RuntimeCeleryHarness.create(broker_url)
        publisher = harness.publisher(auth_database_session)
        outbox = (
            await auth_database_session.scalars(
                select(AnalysisJobOutbox).where(AnalysisJobOutbox.analysis_job_id == job.id)
            )
        ).one()
        outbox.next_attempt_at = datetime.now(UTC)
        assert await publisher.publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        worker.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            await auth_database_session.refresh(job)
            if job.status == AnalysisJobStatus.SUCCEEDED:
                break
            await asyncio.sleep(0.05)
        assert job.status == AnalysisJobStatus.SUCCEEDED
        assert game.analysis_available_at is None
    finally:
        worker.graceful_stop()
        harness.close()
        redis.remove()


@pytest.mark.asyncio
async def test_worker_process_loss_recovers_expired_lease_and_completes_with_new_worker(
    auth_database_session: AsyncSession, tmp_path: Path
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-runtime-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    gate_path = tmp_path / "worker-gate"
    first_worker = CeleryWorkerController(
        database_url,
        {
            "BOARDTRACE_TEST_WORKER_GATE_ENABLED": "1",
            "BOARDTRACE_TEST_WORKER_GATE_PATH": str(gate_path),
            "BOARDTRACE_REDIS_URL": broker_url,
        },
        harness.app,
    )
    second_worker: CeleryWorkerController | None = None
    try:
        redis.start()
        first_worker.start()
        game = await completed_game(auth_database_session)
        job = await AnalysisJobService(auth_database_session).create_for_completed_game(
            game.id, uuid4()
        )
        job_id = job.id
        publisher = harness.publisher(auth_database_session)
        assert await publisher.publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            await auth_database_session.refresh(job)
            if job.status == AnalysisJobStatus.RUNNING:
                break
            await asyncio.sleep(0.05)
        assert job.status == AnalysisJobStatus.RUNNING
        old_worker_id = job.worker_id
        assert old_worker_id is not None and job.lease_expires_at is not None
        first_worker.terminate()
        first_worker.assert_not_running()
        recovered = await AnalysisJobRepository(auth_database_session).recover_expired_lease(
            job_id, datetime.now(UTC) + timedelta(seconds=121), RetryPolicy(30, 900, 0)
        )
        assert recovered is not None and recovered.status == AnalysisJobStatus.RETRY_SCHEDULED
        assert recovered.worker_id is None and recovered.lease_expires_at is None
        assert recovered.heartbeat_at is None
        await auth_database_session.commit()
        retry_outbox = (
            await auth_database_session.scalars(
                select(AnalysisJobOutbox).where(AnalysisJobOutbox.analysis_job_id == job_id)
            )
        ).all()
        assert len(retry_outbox) == 2
        retry_outbox[-1].next_attempt_at = datetime.now(UTC)
        harness.close()
        harness = RuntimeCeleryHarness.create(broker_url)
        publisher = harness.publisher(auth_database_session)
        second_worker = CeleryWorkerController(
            database_url, {"BOARDTRACE_REDIS_URL": broker_url}, harness.app
        )
        assert await publisher.publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        second_worker.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            auth_database_session.expire(job)
            current = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
            if current is not None and current.status == AnalysisJobStatus.SUCCEEDED:
                break
            await asyncio.sleep(0.05)
        auth_database_session.expire(job)
        completed = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
        assert completed is not None and completed.status == AnalysisJobStatus.SUCCEEDED
        assert not await AnalysisJobRepository(auth_database_session).complete_job(
            job_id, old_worker_id, datetime.now(UTC)
        )
    finally:
        first_worker.graceful_stop()
        if second_worker is not None:
            second_worker.graceful_stop()
        harness.close()
        redis.remove()


@pytest.mark.asyncio
async def test_worker_terminal_failure_persists_once_without_retry_or_redelivery(
    auth_database_session: AsyncSession, tmp_path: Path
) -> None:
    database_url = get_test_database_url()
    broker_port = unused_port()
    broker_url = f"redis://127.0.0.1:{broker_port}/0"
    redis = RedisContainerController(f"boardtrace-runtime-{uuid4().hex}", broker_port)
    harness = RuntimeCeleryHarness.create(broker_url)
    gate_path = tmp_path / "terminal-failure-gate"
    worker = CeleryWorkerController(
        database_url,
        {
            "BOARDTRACE_TEST_WORKER_GATE_ENABLED": "1",
            "BOARDTRACE_TEST_WORKER_GATE_PATH": str(gate_path),
            "BOARDTRACE_REDIS_URL": broker_url,
        },
        harness.app,
    )
    try:
        redis.start()
        worker.start()
        game = await completed_game(auth_database_session)
        job = await AnalysisJobService(auth_database_session).create_for_completed_game(
            game.id, uuid4()
        )
        job_id = job.id
        assert await harness.publisher(auth_database_session).publish_due(datetime.now(UTC)) == 1
        await auth_database_session.commit()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            auth_database_session.expire(job)
            persisted = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
            if persisted is not None and persisted.status == AnalysisJobStatus.FAILED:
                break
            await asyncio.sleep(0.1)
        persisted = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
        assert persisted is not None
        assert persisted.status == AnalysisJobStatus.FAILED
        assert persisted.last_error_code == "invalid_job_request"
        assert persisted.worker_id is None
        assert persisted.lease_expires_at is None
        assert (
            await auth_database_session.scalar(
                select(AnalysisJobOutbox).where(AnalysisJobOutbox.analysis_job_id == job_id)
            )
            is not None
        )
        assert (
            len(
                (
                    await auth_database_session.scalars(
                        select(AnalysisJobOutbox).where(AnalysisJobOutbox.analysis_job_id == job_id)
                    )
                ).all()
            )
            == 1
        )
        harness.app.send_task(
            ANALYSIS_TASK,
            kwargs={
                "payload": AnalysisTaskPayload(
                    schema_version=1, job_id=job_id, correlation_id=uuid4()
                ).model_dump(mode="json")
            },
        )
        await asyncio.sleep(1)
        auth_database_session.expire(job)
        duplicate = await AnalysisJobRepository(auth_database_session).get_by_id(job_id)
        assert duplicate is not None and duplicate.status == AnalysisJobStatus.FAILED
        assert (
            len(
                (
                    await auth_database_session.scalars(
                        select(AnalysisJobOutbox).where(AnalysisJobOutbox.analysis_job_id == job_id)
                    )
                ).all()
            )
            == 1
        )
    finally:
        worker.graceful_stop()
        harness.close()
        redis.remove()
