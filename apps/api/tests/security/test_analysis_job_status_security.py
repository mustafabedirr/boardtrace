from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AnalysisJob, Game, User
from boardtrace_api.models.enums import GameResult, GameStatus, PlayerColor
from boardtrace_api.services.analysis_jobs import AnalysisJobService

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.security]


async def owned_job(session: AsyncSession) -> tuple[User, User, AnalysisJob]:
    owner = User(
        email=f"owner-{uuid4()}@example.com",
        normalized_email=f"owner-{uuid4()}@example.com",
        display_name=None,
        password_hash=None,
    )
    other = User(
        email=f"other-{uuid4()}@example.com",
        normalized_email=f"other-{uuid4()}@example.com",
        display_name=None,
        password_hash=None,
    )
    session.add_all([owner, other])
    await session.flush()
    game = Game(
        user_id=owner.id,
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
    job = await AnalysisJobService(session).create_for_completed_game(game.id, uuid4())
    await session.commit()
    return owner, other, job


@pytest.mark.asyncio
async def test_analysis_status_is_owner_scoped_and_safe(
    auth_client: httpx.AsyncClient, auth_database_session: AsyncSession
) -> None:
    owner, other, job = await owned_job(auth_database_session)
    tokens = TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )
    owner_token = tokens.issue_access_token(owner.id)
    other_token = tokens.issue_access_token(other.id)
    response = await auth_client.get(
        f"/api/v1/analysis/jobs/{job.id}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["analysis_available"] is False
    for forbidden in (
        "worker_id",
        "lease_expires_at",
        "heartbeat_at",
        "queue_message_id",
        "last_error_message",
        "evaluation",
        "best_move",
        "principal_variation",
    ):
        assert forbidden not in payload
    denied = await auth_client.get(
        f"/api/v1/analysis/jobs/{job.id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert denied.status_code == 404
    assert (await auth_client.get(f"/api/v1/analysis/jobs/{job.id}")).status_code == 401
    extension_token = tokens.issue_extension_token(
        owner.id, "test-extension", ("games:read-status",)
    )
    assert (
        await auth_client.get(
            f"/api/v1/analysis/jobs/{job.id}",
            headers={"Authorization": f"Bearer {extension_token}"},
        )
    ).status_code == 200
    insufficient = tokens.issue_extension_token(owner.id, "test-extension", ("games:ingest",))
    assert (
        await auth_client.get(
            f"/api/v1/analysis/jobs/{job.id}",
            headers={"Authorization": f"Bearer {insufficient}"},
        )
    ).status_code == 403
