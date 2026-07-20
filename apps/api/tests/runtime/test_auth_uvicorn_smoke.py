import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.postgres_helpers import get_test_database_url

pytestmark = [pytest.mark.database, pytest.mark.integration]

AUTH_PREFIX = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"
TEST_JWT_SECRET = "test-jwt-signing-secret-with-adequate-length"
TEST_REFRESH_PEPPER = "test-refresh-token-pepper"


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        return cast(int, socket_handle.getsockname()[1])


@contextmanager
def uvicorn_process(
    database_url: str, extra_environment: dict[str, str] | None = None
) -> Iterator[tuple[subprocess.Popen[str], str]]:
    port = unused_port()
    environment = (
        os.environ
        | {
            "BOARDTRACE_DATABASE_URL": database_url,
            "BOARDTRACE_JWT_SIGNING_SECRET": TEST_JWT_SECRET,
            "BOARDTRACE_REFRESH_TOKEN_PEPPER": TEST_REFRESH_PEPPER,
            "BOARDTRACE_LOG_FORMAT": "console",
        }
        | (extra_environment or {})
    )
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "boardtrace_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd="apps/api",
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    try:
        yield process, f"http://127.0.0.1:{port}"
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


def wait_for_ready(client: httpx.Client, base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.communicate(timeout=1)[0]
            pytest.fail(f"Uvicorn exited before becoming ready: {output}")
        try:
            response = client.get(f"{base_url}/api/v1/health/ready")
        except httpx.HTTPError:
            time.sleep(0.1)
            continue
        if response.status_code == 200:
            return
        time.sleep(0.1)
    pytest.fail("Uvicorn did not become ready within 15 seconds")


def assert_no_store(response: httpx.Response) -> None:
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


def test_authentication_uvicorn_runtime_smoke(auth_database_session: AsyncSession) -> None:
    database_url = get_test_database_url()
    with uvicorn_process(database_url) as (process, base_url):
        with httpx.Client(timeout=5) as client:
            wait_for_ready(client, base_url, process)
            live = client.get(f"{base_url}/api/v1/health/live")
            ready = client.get(f"{base_url}/api/v1/health/ready")
            openapi = client.get(f"{base_url}/openapi.json")
            assert live.status_code == 200
            assert ready.json() == {
                "status": "ready",
                "checks": {"application": "ok", "database": "ok"},
            }
            assert ready.status_code == 200
            assert openapi.status_code == 200
            assert f"{AUTH_PREFIX}/refresh" in openapi.json()["paths"]

            registration = client.post(
                f"{base_url}{AUTH_PREFIX}/register",
                json={"email": "runtime-alpha@example.com", "password": PASSWORD},
            )
            assert registration.status_code == 200
            assert_no_store(registration)
            initial_pair = registration.json()
            login = client.post(
                f"{base_url}{AUTH_PREFIX}/login",
                json={"email": "runtime-alpha@example.com", "password": PASSWORD},
            )
            assert login.status_code == 200
            assert_no_store(login)
            login_pair = login.json()
            me = client.get(
                f"{base_url}{AUTH_PREFIX}/me",
                headers={"Authorization": f"Bearer {login_pair['access_token']}"},
            )
            assert me.status_code == 200
            assert me.json()["email"] == "runtime-alpha@example.com"

            refresh = client.post(
                f"{base_url}{AUTH_PREFIX}/refresh",
                json={"refresh_token": initial_pair["refresh_token"]},
            )
            assert refresh.status_code == 200
            assert_no_store(refresh)
            refreshed_pair = refresh.json()
            assert refreshed_pair["refresh_token"] != initial_pair["refresh_token"]
            logout = client.post(
                f"{base_url}{AUTH_PREFIX}/logout",
                json={"refresh_token": refreshed_pair["refresh_token"]},
            )
            assert logout.status_code == 200
            assert_no_store(logout)
            revoked_refresh = client.post(
                f"{base_url}{AUTH_PREFIX}/refresh",
                json={"refresh_token": refreshed_pair["refresh_token"]},
            )
            assert revoked_refresh.status_code == 401
            assert revoked_refresh.json()["error"]["code"] == "invalid_refresh_token"

            logout_all = client.post(
                f"{base_url}{AUTH_PREFIX}/logout-all",
                headers={"Authorization": f"Bearer {login_pair['access_token']}"},
            )
            assert logout_all.status_code == 200
            assert_no_store(logout_all)
            revoked_login = client.post(
                f"{base_url}{AUTH_PREFIX}/refresh",
                json={"refresh_token": login_pair["refresh_token"]},
            )
            assert revoked_login.status_code == 401

            unauthenticated = client.get(f"{base_url}{AUTH_PREFIX}/me")
            assert unauthenticated.status_code == 401
            assert unauthenticated.headers["WWW-Authenticate"] == "Bearer"
            assert unauthenticated.json()["error"]["code"] == "authentication_required"

        assert process.poll() is None
    output = process.communicate(timeout=1)[0]
    expected_exit_codes = {0, 3} if os.name == "nt" else {0}
    assert process.returncode in expected_exit_codes, output
    assert "application started" in output
    assert "application stopped" in output
    for secret in (
        TEST_JWT_SECRET,
        TEST_REFRESH_PEPPER,
        PASSWORD,
        initial_pair["refresh_token"],
        login_pair["access_token"],
    ):
        assert secret not in output
