from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
async def test_logout_revokes_only_the_target_session_and_rejects_its_refresh_token(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, target_pair = await service.register(
        "logout-target@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user_id = user.id
    sibling_pair = await service.login("logout-target@example.test", "correct-horse-battery-staple")
    await auth_database_session.commit()
    _, other_pair = await service.register(
        "logout-other@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()

    target_digest = tokens.digest_refresh_token(target_pair.refresh_token)
    sibling_digest = tokens.digest_refresh_token(sibling_pair.refresh_token)
    other_digest = tokens.digest_refresh_token(other_pair.refresh_token)
    await service.revoke(target_pair.refresh_token)
    await auth_database_session.commit()
    auth_database_session.expire_all()

    target = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == target_digest)
    )
    sibling = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == sibling_digest)
    )
    other = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == other_digest)
    )
    assert target is not None
    assert target.revoked_at is not None
    assert target.revoked_at.tzinfo is not None
    assert sibling is not None
    assert sibling.user_id == user_id
    assert sibling.revoked_at is None
    assert other is not None
    assert other.user_id != user_id
    assert other.revoked_at is None
    first_revocation = target.revoked_at

    await service.revoke(target_pair.refresh_token)
    await service.revoke("unknown-refresh-token")
    await auth_database_session.commit()
    auth_database_session.expire_all()
    repeated_target = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == target_digest)
    )
    assert repeated_target is not None
    assert repeated_target.revoked_at == first_revocation

    with pytest.raises(AuthenticationError) as error:
        await service.refresh(target_pair.refresh_token)
    assert str(error.value) == ""
    await auth_database_session.commit()
    target_user_sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    assert len(target_user_sessions) == 2


@pytest.mark.asyncio
async def test_logout_rollback_leaves_the_target_session_active(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    _, pair = await service.register(
        "logout-rollback@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    digest = tokens.digest_refresh_token(pair.refresh_token)

    await service.revoke(pair.refresh_token)
    await auth_database_session.rollback()

    target = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == digest)
    )
    assert target is not None
    assert target.revoked_at is None


@pytest.mark.asyncio
async def test_logout_all_revokes_active_and_expired_sessions_without_cross_user_effects(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, pre_revoked_pair = await service.register(
        "logout-all@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user_id = user.id
    active_pair = await service.login("logout-all@example.test", "correct-horse-battery-staple")
    await auth_database_session.commit()
    expired_pair = await service.login("logout-all@example.test", "correct-horse-battery-staple")
    await auth_database_session.commit()
    _, other_pair = await service.register(
        "logout-all-other@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()

    pre_revoked_digest = tokens.digest_refresh_token(pre_revoked_pair.refresh_token)
    expired_digest = tokens.digest_refresh_token(expired_pair.refresh_token)
    other_digest = tokens.digest_refresh_token(other_pair.refresh_token)
    pre_revoked = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == pre_revoked_digest)
    )
    expired = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == expired_digest)
    )
    assert pre_revoked is not None
    assert expired is not None
    original_revocation = datetime.now(UTC) - timedelta(minutes=1)
    pre_revoked.revoked_at = original_revocation
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_database_session.commit()

    await service.revoke_all(user_id)
    await service.revoke_all(uuid4())
    await auth_database_session.commit()
    auth_database_session.expire_all()

    user_sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    other = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == other_digest)
    )
    assert len(user_sessions) == 3
    assert all(auth_session.revoked_at is not None for auth_session in user_sessions)
    refreshed_pre_revoked = next(
        auth_session
        for auth_session in user_sessions
        if auth_session.token_digest == pre_revoked_digest
    )
    assert refreshed_pre_revoked.revoked_at == original_revocation
    assert other is not None
    assert other.revoked_at is None

    with pytest.raises(AuthenticationError):
        await service.refresh(active_pair.refresh_token)
    await auth_database_session.commit()
    auth_database_session.expire_all()
    user_sessions_after_refresh_attempt = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    assert len(user_sessions_after_refresh_attempt) == 3


@pytest.mark.asyncio
async def test_logout_all_rollback_keeps_every_session_active(
    auth_database_session: AsyncSession,
) -> None:
    service, _ = create_service(auth_database_session)
    user, _ = await service.register(
        "logout-all-rollback@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    await service.login("logout-all-rollback@example.test", "correct-horse-battery-staple")
    await auth_database_session.commit()
    user_id = user.id

    await service.revoke_all(user_id)
    await auth_database_session.rollback()

    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    assert len(sessions) == 2
    assert all(auth_session.revoked_at is None for auth_session in sessions)
