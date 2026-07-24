from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import (
    AnalysisMoveEvaluation,
    AnalysisPositionEvaluation,
    AnalysisRun,
    Game,
    User,
)
from boardtrace_api.models.enums import GameStatus
from tests.integration.test_internal_analysis_reads import _completed_snapshot

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.security]

FORBIDDEN_PUBLIC_KEYS = {
    "analysis_run_id",
    "job_id",
    "lease_generation",
    "analysis_version",
    "owner_user_id",
    "position_id",
    "engine_name",
    "engine_version",
    "configuration_snapshot",
    "evaluation",
    "score",
    "mate_in",
    "mate_score",
    "best_move",
    "best_move_uci",
    "principal_variation",
    "principal_variation_uci",
    "reference_best_move_uci",
    "centipawn_delta",
    "raw_centipawn_loss",
    "classification_reason",
}


def _token(user_id: UUID) -> str:
    return TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    ).issue_access_token(user_id)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


async def _counts(session: AsyncSession) -> tuple[int | None, ...]:
    return (
        await session.scalar(select(func.count(AnalysisRun.id))),
        await session.scalar(select(func.count(AnalysisPositionEvaluation.id))),
        await session.scalar(select(func.count(AnalysisMoveEvaluation.id))),
    )


@pytest.mark.asyncio
async def test_owner_reads_released_current_analysis_through_public_dto_only(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.ANALYSIS_AVAILABLE
    await auth_database_session.commit()
    before = await _counts(auth_database_session)

    response = await auth_client.get(
        f"/api/v1/analysis/games/{job.game_id}",
        headers={"Authorization": f"Bearer {_token(job.owner_user_id)}"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    payload = response.json()
    assert set(payload) == {"game_id", "moves", "white", "black"}
    assert payload["game_id"] == str(job.game_id)
    assert tuple(move["ply"] for move in payload["moves"]) == (1, 2)
    assert set(payload["moves"][0]) == {
        "ply",
        "move_uci",
        "move_san",
        "mover",
        "quality",
        "centipawn_loss",
    }
    assert payload["moves"][0]["quality"] == "BEST"
    assert payload["white"]["accuracy"] == "99.01"
    assert payload["black"]["accuracy"] == "97.09"
    assert _all_keys(payload).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
    assert await _counts(auth_database_session) == before


@pytest.mark.asyncio
async def test_public_analysis_is_owner_only_and_web_token_only(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = GameStatus.ANALYSIS_AVAILABLE
    await auth_database_session.commit()
    tokens = TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )
    other = User(
        email=f"analysis-reader-{uuid4()}@example.test",
        normalized_email=f"analysis-reader-{uuid4()}@example.test",
        display_name=None,
        password_hash=None,
    )
    auth_database_session.add(other)
    await auth_database_session.commit()

    assert (
        await auth_client.get(
            f"/api/v1/analysis/games/{job.game_id}",
            headers={"Authorization": f"Bearer {tokens.issue_access_token(other.id)}"},
        )
    ).status_code == 404
    assert (await auth_client.get(f"/api/v1/analysis/games/{job.game_id}")).status_code == 401
    extension_token = tokens.issue_extension_token(
        job.owner_user_id,
        "test-extension",
        ("games:read-status",),
    )
    assert (
        await auth_client.get(
            f"/api/v1/analysis/games/{job.game_id}",
            headers={"Authorization": f"Bearer {extension_token}"},
        )
    ).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        GameStatus.FINISHED,
        GameStatus.DEEP_ANALYSIS_RUNNING,
    ],
)
async def test_public_analysis_stays_locked_before_analysis_available(
    status: GameStatus,
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    job, _ = await _completed_snapshot(auth_database_session)
    game = await auth_database_session.get(Game, job.game_id)
    assert game is not None
    game.status = status
    await auth_database_session.commit()

    response = await auth_client.get(
        f"/api/v1/analysis/games/{job.game_id}",
        headers={"Authorization": f"Bearer {_token(job.owner_user_id)}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
