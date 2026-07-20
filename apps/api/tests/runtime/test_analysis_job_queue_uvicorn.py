import hashlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.queue import ANALYSIS_TASK, OUTBOX_PUBLISH_TASK
from boardtrace_api.worker import celery_app
from tests.postgres_helpers import get_test_database_url
from tests.runtime.test_auth_uvicorn_smoke import (
    AUTH_PREFIX,
    PASSWORD,
    TEST_JWT_SECRET,
    TEST_REFRESH_PEPPER,
    assert_no_store,
    uvicorn_process,
    wait_for_ready,
)

pytestmark = [
    pytest.mark.database,
    pytest.mark.integration,
    pytest.mark.queue,
    pytest.mark.runtime,
]


@contextmanager
def celery_worker_process(database_url: str) -> Iterator[subprocess.Popen[str]]:
    environment = os.environ | {
        "BOARDTRACE_DATABASE_URL": database_url,
        "BOARDTRACE_JWT_SIGNING_SECRET": TEST_JWT_SECRET,
        "BOARDTRACE_REFRESH_TOKEN_PEPPER": TEST_REFRESH_PEPPER,
        "BOARDTRACE_LOG_FORMAT": "console",
    }
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "boardtrace_api.worker:celery_app",
            "worker",
            "--pool=solo",
            "--loglevel=WARNING",
            "--hostname=boardtrace-runtime@%h",
        ],
        cwd="apps/api",
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.communicate(timeout=1)[0]
                pytest.fail(f"Celery worker exited before readiness: {output}")
            inspector = celery_app.control.inspect(timeout=0.5)
            if inspector.ping():
                yield process
                return
            time.sleep(0.1)
        pytest.fail("Celery worker did not become ready within 15 seconds")
    finally:
        if process.poll() is None:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        process.communicate(timeout=1)


def wait_for_job_status(
    client: httpx.Client, base_url: str, token: str, job_id: str
) -> dict[str, object]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(
            f"{base_url}/api/v1/analysis/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200 and response.json()["status"] == "SUCCEEDED":
            return dict(response.json())
        time.sleep(0.1)
    pytest.fail("Analysis job did not reach SUCCEEDED within 15 seconds")


def test_analysis_job_queue_runtime_smoke(auth_database_session: AsyncSession) -> None:
    database_url = get_test_database_url()
    with (
        celery_worker_process(database_url) as worker,
        uvicorn_process(database_url) as (
            server,
            base_url,
        ),
    ):
        with httpx.Client(timeout=5) as client:
            wait_for_ready(client, base_url, server)
            owner = client.post(
                f"{base_url}{AUTH_PREFIX}/register",
                json={"email": "runtime-analysis-owner@example.com", "password": PASSWORD},
            )
            assert owner.status_code == 200
            assert_no_store(owner)
            web_token = owner.json()["access_token"]
            pairing = client.post(
                f"{base_url}/api/v1/extension-pairings",
                headers={"Authorization": f"Bearer {web_token}"},
                json={
                    "extension_id": "runtime-analysis",
                    "scopes": ["games:ingest", "games:read-status"],
                },
            )
            code = pairing.json()["code"]
            extension = client.post(
                f"{base_url}/api/v1/extension-pairings/exchange",
                json={"code": code, "extension_id": "runtime-analysis"},
            )
            extension_token = extension.json()["access_token"]
            payload = {
                "idempotency_key": hashlib.sha256(b"runtime-analysis-job").hexdigest(),
                "platform": "lichess",
                "source_game_id": "RuntimeQueue1",
                "completed_at": "2026-07-18T10:00:00Z",
                "player_color": "UNKNOWN",
                "result": "UNKNOWN",
                "initial_fen": None,
                "moves": ["e2e4"],
            }
            ingestion = client.post(
                f"{base_url}/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {extension_token}"},
                json=payload,
            )
            assert ingestion.status_code == 201
            job_id = ingestion.json()["analysis_job_id"]
            celery_app.send_task(OUTBOX_PUBLISH_TASK)
            status = wait_for_job_status(client, base_url, web_token, job_id)
            assert status["analysis_available"] is False
            assert set(status).isdisjoint({"evaluation", "best_move", "principal_variation"})
            duplicate = client.post(
                f"{base_url}/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {extension_token}"},
                json=payload,
            )
            assert duplicate.status_code == 201
            assert duplicate.json()["analysis_job_id"] == job_id
            celery_app.send_task(
                ANALYSIS_TASK,
                kwargs={
                    "payload": {
                        "schema_version": 1,
                        "job_id": job_id,
                        "correlation_id": str(uuid4()),
                    }
                },
            )
            time.sleep(0.3)
            assert wait_for_job_status(client, base_url, web_token, job_id)["status"] == "SUCCEEDED"
            second = client.post(
                f"{base_url}{AUTH_PREFIX}/register",
                json={"email": "runtime-analysis-other@example.com", "password": PASSWORD},
            )
            forbidden = client.get(
                f"{base_url}/api/v1/analysis/jobs/{job_id}",
                headers={"Authorization": f"Bearer {second.json()['access_token']}"},
            )
            assert forbidden.status_code == 404
        assert server.poll() is None
        assert worker.poll() is None
    server.communicate(timeout=1)
