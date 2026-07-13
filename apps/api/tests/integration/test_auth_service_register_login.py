from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationError, AuthenticationService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AuthSession, User

pytestmark = [pytest.mark.database, pytest.mark.integration]


def create_service(
    session: AsyncSession,
) -> tuple[AuthenticationService, PasswordService, TokenService]:
    passwords = PasswordService()
    tokens = TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )
    return AuthenticationService(session, passwords, tokens), passwords, tokens


@pytest.mark.asyncio
async def test_register_normalizes_email_hashes_password_and_creates_session(
    auth_database_session: AsyncSession,
) -> None:
    service, passwords, tokens = create_service(auth_database_session)

    user, pair = await service.register(
        "  Register.User@Example.Test  ",
        "correct-horse-battery-staple",
        "Registered User",
    )
    await auth_database_session.commit()

    stored_user = await auth_database_session.get(User, user.id)
    stored_session = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.user_id == user.id)
    )
    assert stored_user is not None
    assert stored_user.email == "Register.User@Example.Test"
    assert stored_user.normalized_email == "register.user@example.test"
    assert stored_user.password_hash is not None
    assert stored_user.password_hash != "correct-horse-battery-staple"
    assert passwords.verify("correct-horse-battery-staple", stored_user.password_hash)
    assert stored_user.email_verified is False
    assert stored_session is not None
    assert stored_session.token_digest == tokens.digest_refresh_token(pair.refresh_token)
    assert pair.refresh_token not in stored_session.token_digest


@pytest.mark.asyncio
async def test_register_rejects_duplicate_normalized_email_and_keeps_transaction_ownership(
    auth_database_session: AsyncSession,
) -> None:
    service, _, _ = create_service(auth_database_session)
    await service.register("duplicate@example.test", "correct-horse-battery-staple", None)
    await auth_database_session.commit()

    with pytest.raises(AuthenticationError):
        await service.register(" DUPLICATE@EXAMPLE.TEST ", "correct-horse-battery-staple", None)

    await service.register("rollback@example.test", "correct-horse-battery-staple", None)
    await auth_database_session.rollback()

    rolled_back_user = await auth_database_session.scalar(
        select(User).where(User.normalized_email == "rollback@example.test")
    )
    assert rolled_back_user is None


@pytest.mark.asyncio
async def test_login_updates_last_login_and_creates_a_digest_only_session(
    auth_database_session: AsyncSession,
) -> None:
    service, _, tokens = create_service(auth_database_session)
    user, _ = await service.register("login@example.test", "correct-horse-battery-staple", None)
    await auth_database_session.commit()

    pair = await service.login(" LOGIN@EXAMPLE.TEST ", "correct-horse-battery-staple")
    await auth_database_session.commit()
    await auth_database_session.refresh(user)
    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user.id)
            )
        ).all()
    )

    assert user.last_login_at is not None
    assert user.last_login_at.tzinfo is not None
    assert user.last_login_at <= datetime.now(UTC)
    assert user.email_verified is False
    assert len(sessions) == 2
    refresh_digest = tokens.digest_refresh_token(pair.refresh_token)
    assert any(session.token_digest == refresh_digest for session in sessions)
    assert all(pair.refresh_token not in session.token_digest for session in sessions)


@pytest.mark.asyncio
async def test_login_rejects_wrong_password_unknown_and_inactive_users(
    auth_database_session: AsyncSession,
) -> None:
    service, _, _ = create_service(auth_database_session)
    user, _ = await service.register("inactive@example.test", "correct-horse-battery-staple", None)
    await auth_database_session.commit()

    with pytest.raises(AuthenticationError):
        await service.login("inactive@example.test", "wrong-password-value")
    with pytest.raises(AuthenticationError):
        await service.login("unknown@example.test", "correct-horse-battery-staple")

    user.is_active = False
    await auth_database_session.commit()
    with pytest.raises(AuthenticationError):
        await service.login("inactive@example.test", "correct-horse-battery-staple")
