from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationError, AuthenticationService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AuthSession

pytestmark = [pytest.mark.database, pytest.mark.integration]


def create_service(
    session: AsyncSession,
) -> tuple[AuthenticationService, TokenService]:
    tokens = TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )
    return AuthenticationService(session, PasswordService(), tokens), tokens


@pytest.mark.asyncio
async def test_refresh_rotates_session_preserves_family_and_links_replacement(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, initial_pair = await service.register(
        "refresh-success@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    parent = await auth_database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_digest == tokens.digest_refresh_token(initial_pair.refresh_token)
        )
    )
    assert parent is not None
    parent_family_id = parent.family_id

    refreshed_pair = await service.refresh(initial_pair.refresh_token)
    await auth_database_session.commit()
    await auth_database_session.refresh(parent)
    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user.id)
            )
        ).all()
    )
    replacement_digest = tokens.digest_refresh_token(refreshed_pair.refresh_token)
    replacement = next(
        (
            auth_session
            for auth_session in sessions
            if auth_session.token_digest == replacement_digest
        ),
        None,
    )

    assert refreshed_pair.refresh_token != initial_pair.refresh_token
    assert tokens.decode_access_token(refreshed_pair.access_token) == user.id
    assert parent.revoked_at is not None
    assert parent.revoked_at.tzinfo is not None
    assert parent.replaced_by_session_id is not None
    assert replacement is not None
    assert replacement.id == parent.replaced_by_session_id
    assert replacement.user_id == user.id
    assert replacement.family_id == parent_family_id
    assert replacement.expires_at > datetime.now(UTC)
    assert all(initial_pair.refresh_token not in item.token_digest for item in sessions)
    assert all(refreshed_pair.refresh_token not in item.token_digest for item in sessions)


@pytest.mark.asyncio
async def test_refresh_rolls_back_parent_revocation_and_replacement_creation(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, initial_pair = await service.register(
        "refresh-rollback@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    parent_digest = tokens.digest_refresh_token(initial_pair.refresh_token)
    user_id = user.id

    await service.refresh(initial_pair.refresh_token)
    await auth_database_session.rollback()

    parent = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == parent_digest)
    )
    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    assert parent is not None
    assert parent.revoked_at is None
    assert parent.replaced_by_session_id is None
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_refresh_rejects_unknown_expired_and_revoked_sessions(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    with pytest.raises(AuthenticationError) as unknown_error:
        await service.refresh("unknown-refresh-token")
    assert str(unknown_error.value) == ""

    _, expired_pair = await service.register(
        "refresh-expired@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    expired_session = await auth_database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_digest == tokens.digest_refresh_token(expired_pair.refresh_token)
        )
    )
    assert expired_session is not None
    expired_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_database_session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(expired_pair.refresh_token)

    _, revoked_pair = await service.register(
        "refresh-revoked@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    revoked_session = await auth_database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_digest == tokens.digest_refresh_token(revoked_pair.refresh_token)
        )
    )
    assert revoked_session is not None
    revoked_session.revoked_at = datetime.now(UTC)
    await auth_database_session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(revoked_pair.refresh_token)


@pytest.mark.asyncio
async def test_refresh_rejects_an_inactive_session_user(
    auth_database_session: AsyncSession,
) -> None:
    service, _ = create_service(auth_database_session)
    user, pair = await service.register(
        "refresh-inactive@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user.is_active = False
    await auth_database_session.commit()

    with pytest.raises(AuthenticationError):
        await service.refresh(pair.refresh_token)
