from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import Game, User
from boardtrace_api.models.enums import GameResult, GameStatus, PlayerColor

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.security]


def _tokens() -> TokenService:
    return TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )


async def _game(
    session: AsyncSession,
    lifecycle: GameStatus,
    completion_verified: bool,
) -> tuple[User, Game]:
    owner = User(
        email=f"lifecycle-{uuid4()}@example.test",
        normalized_email=f"lifecycle-{uuid4()}@example.test",
        display_name=None,
        password_hash=None,
    )
    session.add(owner)
    await session.flush()
    game = Game(
        user_id=owner.id,
        status=lifecycle,
        platform="test",
        player_color=PlayerColor.UNKNOWN,
        result=GameResult.UNKNOWN,
        completion_verified_at=datetime.now(UTC) if completion_verified else None,
        normalized_moves=[],
        source_game_id=str(uuid4()),
    )
    session.add(game)
    await session.commit()
    return owner, game


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lifecycle", "verified"),
    [
        (GameStatus.CREATED, False),
        (GameStatus.CAPTURING, False),
        (GameStatus.FINISH_PENDING, False),
        (GameStatus.FINISHED, True),
        (GameStatus.DEEP_ANALYSIS_RUNNING, True),
        (GameStatus.ANALYSIS_AVAILABLE, True),
        (GameStatus.FAILED, True),
    ],
)
async def test_owner_reads_exact_authoritative_lifecycle_without_analysis_metadata(
    lifecycle: GameStatus,
    verified: bool,
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    owner, game = await _game(auth_database_session, lifecycle, verified)

    response = await auth_client.get(
        f"/api/v1/games/{game.id}/lifecycle",
        headers={"Authorization": f"Bearer {_tokens().issue_access_token(owner.id)}"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.json() == {
        "game_id": str(game.id),
        "lifecycle": lifecycle.value,
        "completion_verified": verified,
    }


@pytest.mark.asyncio
async def test_lifecycle_read_is_owner_only_and_rejects_extension_tokens(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    owner, game = await _game(auth_database_session, GameStatus.FINISHED, True)
    other, _ = await _game(auth_database_session, GameStatus.FINISHED, True)
    tokens = _tokens()
    url = f"/api/v1/games/{game.id}/lifecycle"

    assert (
        await auth_client.get(
            url,
            headers={"Authorization": f"Bearer {tokens.issue_access_token(other.id)}"},
        )
    ).status_code == 404
    assert (await auth_client.get(url)).status_code == 401
    extension_token = tokens.issue_extension_token(
        owner.id,
        "test-extension",
        ("games:read-status",),
    )
    assert (
        await auth_client.get(
            url,
            headers={"Authorization": f"Bearer {extension_token}"},
        )
    ).status_code == 401
