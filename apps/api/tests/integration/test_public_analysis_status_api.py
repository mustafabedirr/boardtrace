from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AnalysisJob, AnalysisRun, Game, User
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisJobType, GameStatus
from tests.integration.test_internal_analysis_reads import _completed_snapshot

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.security]


def _tokens() -> TokenService:
    return TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )


async def _durable_counts(session: AsyncSession) -> tuple[int | None, ...]:
    return (
        await session.scalar(select(func.count(Game.id))),
        await session.scalar(select(func.count(AnalysisJob.id))),
        await session.scalar(select(func.count(AnalysisRun.id))),
    )


@pytest.mark.asyncio
async def test_ready_status_is_bounded_and_contains_no_result_or_internal_metadata(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.ANALYSIS_AVAILABLE
    await auth_database_session.commit()
    before = await _durable_counts(auth_database_session)

    response = await auth_client.get(
        f"/api/v1/analysis/games/{job.game_id}/status",
        headers={"Authorization": f"Bearer {_tokens().issue_access_token(job.owner_user_id)}"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert "Retry-After" not in response.headers
    assert response.json() == {
        "game_id": str(job.game_id),
        "readiness": "READY",
        "result_available": True,
        "polling": {
            "should_retry": False,
            "retry_after_ms": None,
            "minimum_interval_ms": 2000,
            "maximum_interval_ms": 15000,
            "backoff_multiplier": 1.5,
        },
    }
    assert await _durable_counts(auth_database_session) == before


@pytest.mark.asyncio
async def test_newer_current_job_prevents_historical_ready_fallback(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    old_job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, old_job.game_id)
    assert game is not None
    game.status = GameStatus.ANALYSIS_AVAILABLE
    current = AnalysisJob(
        game_id=old_job.game_id,
        owner_user_id=old_job.owner_user_id,
        position_id=None,
        job_type=AnalysisJobType.REPORT,
        status=AnalysisJobStatus.PENDING,
        attempts=0,
        attempt_count=0,
        max_attempts=3,
        analysis_profile="standard",
        analysis_version=2,
        lease_generation=0,
    )
    auth_database_session.add(current)
    await auth_database_session.commit()

    response = await auth_client.get(
        f"/api/v1/analysis/games/{old_job.game_id}/status",
        headers={"Authorization": f"Bearer {_tokens().issue_access_token(old_job.owner_user_id)}"},
    )

    assert response.status_code == 200
    assert response.headers["Retry-After"] == "2"
    payload = response.json()
    assert payload["readiness"] == "QUEUED"
    assert payload["result_available"] is False
    assert payload["polling"]["should_retry"] is True
    assert payload["polling"]["retry_after_ms"] == 2000
    serialized = str(payload)
    for forbidden in (
        str(old_job.id),
        str(current.id),
        "analysis_version",
        "lease_generation",
        "attempt",
        "worker",
        "error",
        "moves",
        "accuracy",
        "centipawn",
        "quality",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_retry_lifecycle_is_encapsulated_as_queued_with_existing_delay(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.FINISHED
    job.status = AnalysisJobStatus.RETRY_SCHEDULED
    await auth_database_session.commit()

    response = await auth_client.get(
        f"/api/v1/analysis/games/{job.game_id}/status",
        headers={"Authorization": f"Bearer {_tokens().issue_access_token(job.owner_user_id)}"},
    )

    assert response.status_code == 200
    assert response.headers["Retry-After"] == "5"
    payload = response.json()
    assert payload["readiness"] == "QUEUED"
    assert payload["polling"]["retry_after_ms"] == 5000
    assert "RETRY" not in str(payload)


@pytest.mark.asyncio
async def test_status_is_owner_only_normal_token_only_and_post_game_only(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    other = User(
        email=f"status-reader-{uuid4()}@example.test",
        normalized_email=f"status-reader-{uuid4()}@example.test",
        display_name=None,
        password_hash=None,
    )
    auth_database_session.add(other)
    await auth_database_session.commit()
    tokens = _tokens()
    url = f"/api/v1/analysis/games/{job.game_id}/status"

    assert (
        await auth_client.get(
            url,
            headers={"Authorization": f"Bearer {tokens.issue_access_token(other.id)}"},
        )
    ).status_code == 404
    assert (await auth_client.get(url)).status_code == 401
    extension_token = tokens.issue_extension_token(
        job.owner_user_id,
        "test-extension",
        ("games:read-status",),
    )
    assert (
        await auth_client.get(
            url,
            headers={"Authorization": f"Bearer {extension_token}"},
        )
    ).status_code == 401

    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.CAPTURING
    await auth_database_session.commit()
    assert (
        await auth_client.get(
            url,
            headers={"Authorization": f"Bearer {tokens.issue_access_token(job.owner_user_id)}"},
        )
    ).status_code == 404
