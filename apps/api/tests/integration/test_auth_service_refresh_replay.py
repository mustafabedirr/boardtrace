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
async def test_refresh_replay_compromises_only_the_replayed_session_family(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, root_pair = await service.register(
        "replay-chain@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    root_digest = tokens.digest_refresh_token(root_pair.refresh_token)
    root_session = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == root_digest)
    )
    assert root_session is not None
    family_id = root_session.family_id

    first_pair = await service.refresh(root_pair.refresh_token)
    await auth_database_session.commit()
    await service.refresh(first_pair.refresh_token)
    await auth_database_session.commit()
    same_user_other_family_pair = await service.login(
        "replay-chain@example.test",
        "correct-horse-battery-staple",
    )
    await auth_database_session.commit()
    _, other_user_pair = await service.register(
        "replay-other-user@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()

    family_sessions_before = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.family_id == family_id)
            )
        ).all()
    )
    with pytest.raises(AuthenticationError) as replay_error:
        await service.refresh(root_pair.refresh_token)
    assert str(replay_error.value) == ""
    await auth_database_session.commit()

    family_sessions_after = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.family_id == family_id)
            )
        ).all()
    )
    same_user_other_family = await auth_database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_digest
            == tokens.digest_refresh_token(same_user_other_family_pair.refresh_token)
        )
    )
    other_user_session = await auth_database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_digest == tokens.digest_refresh_token(other_user_pair.refresh_token)
        )
    )
    assert len(family_sessions_after) == len(family_sessions_before)
    assert all(auth_session.revoked_at is not None for auth_session in family_sessions_after)
    assert same_user_other_family is not None
    assert same_user_other_family.user_id == user.id
    assert same_user_other_family.family_id != family_id
    assert same_user_other_family.revoked_at is None
    assert other_user_session is not None
    assert other_user_session.user_id != user.id
    assert other_user_session.revoked_at is None

    with pytest.raises(AuthenticationError):
        await service.refresh(root_pair.refresh_token)
    await auth_database_session.commit()
    family_sessions_after_second_replay = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.family_id == family_id)
            )
        ).all()
    )
    assert len(family_sessions_after_second_replay) == len(family_sessions_after)
    assert all(
        auth_session.revoked_at is not None for auth_session in family_sessions_after_second_replay
    )


@pytest.mark.asyncio
async def test_refresh_replay_family_revocation_is_rollback_atomic(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, root_pair = await service.register(
        "replay-rollback@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    replacement_pair = await service.refresh(root_pair.refresh_token)
    await auth_database_session.commit()
    replacement_digest = tokens.digest_refresh_token(replacement_pair.refresh_token)
    user_id = user.id

    with pytest.raises(AuthenticationError):
        await service.refresh(root_pair.refresh_token)
    await auth_database_session.rollback()

    replacement = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == replacement_digest)
    )
    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    assert replacement is not None
    assert replacement.revoked_at is None
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_expired_refresh_does_not_compromise_an_active_family_member(
    auth_database_session: AsyncSession,
) -> None:
    service, tokens = create_service(auth_database_session)
    user, expired_pair = await service.register(
        "replay-expired@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    expired_digest = tokens.digest_refresh_token(expired_pair.refresh_token)
    expired_session = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == expired_digest)
    )
    assert expired_session is not None
    sibling_pair = await service.issue_pair(user, expired_session.family_id)
    await auth_database_session.commit()
    sibling_digest = tokens.digest_refresh_token(sibling_pair.refresh_token)

    expired_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_database_session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(expired_pair.refresh_token)
    await auth_database_session.commit()

    sibling = await auth_database_session.scalar(
        select(AuthSession).where(AuthSession.token_digest == sibling_digest)
    )
    assert sibling is not None
    assert sibling.revoked_at is None
