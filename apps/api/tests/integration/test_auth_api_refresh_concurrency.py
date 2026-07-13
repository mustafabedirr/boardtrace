import asyncio
from typing import cast

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AuthSession

pytestmark = [pytest.mark.database, pytest.mark.integration]

AUTH_PREFIX = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"


def token_service() -> TokenService:
    return TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )


async def register(auth_client: httpx.AsyncClient, email: str) -> dict[str, object]:
    response = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


async def refresh_after_start(
    auth_client: httpx.AsyncClient,
    refresh_token: str,
    start: asyncio.Event,
) -> httpx.Response:
    await start.wait()
    return await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": refresh_token},
    )


@pytest.mark.asyncio
async def test_concurrent_http_refresh_compromises_only_the_replayed_family(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    root_pair = await register(auth_client, "api-concurrent-refresh@example.com")
    sibling_pair = await register(auth_client, "api-concurrent-refresh-other@example.com")
    same_user_other_family = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "api-concurrent-refresh@example.com", "password": PASSWORD},
    )
    assert same_user_other_family.status_code == 200

    root_refresh_token = str(root_pair["refresh_token"])
    start = asyncio.Event()
    first = asyncio.create_task(refresh_after_start(auth_client, root_refresh_token, start))
    second = asyncio.create_task(refresh_after_start(auth_client, root_refresh_token, start))
    start.set()
    responses = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    successful = [response for response in responses if response.status_code == 200]
    rejected = [response for response in responses if response.status_code == 401]
    assert len(successful) == 1
    assert len(rejected) == 1
    success, rejection = successful[0], rejected[0]
    assert success.headers["Cache-Control"] == "no-store"
    assert success.headers["Pragma"] == "no-cache"
    assert set(success.json()) == {
        "access_token",
        "refresh_token",
        "token_type",
        "expires_in",
    }
    assert rejection.json()["error"]["code"] == "invalid_refresh_token"
    assert root_refresh_token not in rejection.text

    tokens = token_service()
    root_digest = tokens.digest_refresh_token(root_refresh_token)
    auth_database_session.expire_all()
    parent = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == root_digest)
    )
    assert parent is not None
    family_sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.family_id == parent.family_id)
            )
        ).all()
    )
    assert len(family_sessions) == 2
    assert parent.replaced_by_session_id is not None
    assert {session.id for session in family_sessions} == {
        parent.id,
        parent.replaced_by_session_id,
    }
    assert all(session.revoked_at is not None for session in family_sessions)
    assert all(root_refresh_token not in session.token_digest for session in family_sessions)

    successful_refresh_token = str(success.json()["refresh_token"])
    compromised_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": successful_refresh_token},
    )
    assert compromised_refresh.status_code == 401
    assert compromised_refresh.json()["error"]["code"] == "invalid_refresh_token"

    same_user_other_family_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": same_user_other_family.json()["refresh_token"]},
    )
    other_user_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": sibling_pair["refresh_token"]},
    )
    assert same_user_other_family_refresh.status_code == 200
    assert other_user_refresh.status_code == 200
