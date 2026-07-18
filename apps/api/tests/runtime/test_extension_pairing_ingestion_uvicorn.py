import hashlib
import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.postgres_helpers import get_test_database_url
from tests.runtime.test_auth_uvicorn_smoke import (
    AUTH_PREFIX,
    PASSWORD,
    assert_no_store,
    uvicorn_process,
    wait_for_ready,
)

pytestmark = [pytest.mark.database, pytest.mark.integration]


def test_extension_pairing_ingestion_runtime_smoke(auth_database_session: AsyncSession) -> None:
    with uvicorn_process(get_test_database_url()) as (process, base_url):
        with httpx.Client(timeout=5) as client:
            wait_for_ready(client, base_url, process)
            registration = client.post(
                f"{base_url}{AUTH_PREFIX}/register",
                json={"email": "runtime-extension@example.com", "password": PASSWORD},
            )
            assert registration.status_code == 200
            web_token = registration.json()["access_token"]
            pairing = client.post(
                f"{base_url}/api/v1/extension-pairings",
                headers={"Authorization": f"Bearer {web_token}"},
                json={
                    "extension_id": "runtime-extension",
                    "scopes": ["games:ingest", "games:read-status"],
                },
            )
            assert pairing.status_code == 200
            code = pairing.json()["code"]
            exchange = client.post(
                f"{base_url}/api/v1/extension-pairings/exchange",
                json={"code": code, "extension_id": "runtime-extension"},
            )
            assert exchange.status_code == 200
            assert_no_store(exchange)
            extension_token = exchange.json()["access_token"]
            payload = {
                "idempotency_key": hashlib.sha256(b"runtime-extension").hexdigest(),
                "platform": "lichess",
                "source_game_id": "AbCd1234",
                "completed_at": "2026-07-13T10:00:00Z",
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
            assert ingestion.json()["analysis_available"] is False
            duplicate = client.post(
                f"{base_url}/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {extension_token}"},
                json=payload,
            )
            assert duplicate.status_code == 201
            game_id = ingestion.json()["id"]
            status = client.get(
                f"{base_url}/api/v1/games/{game_id}/ingestion-status",
                headers={"Authorization": f"Bearer {extension_token}"},
            )
            assert status.status_code == 200
            assert status.json()["analysis_available"] is False
        assert process.poll() is None
    output = process.communicate(timeout=1)[0]
    expected_exit_codes = {0, 3} if os.name == "nt" else {0}
    assert process.returncode in expected_exit_codes, output
