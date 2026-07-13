from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AuthSession, User
from boardtrace_api.repositories import AuthSessionRepository

pytestmark = [pytest.mark.database, pytest.mark.integration]


async def create_user(session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        normalized_email=email,
        password_hash="argon2-synthetic-hash",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_family_revoke_is_isolated_includes_expired_sessions_and_is_commit_free(
    auth_database_session: AsyncSession,
) -> None:
    target_user = await create_user(auth_database_session, "family-revoke-target@example.test")
    other_user = await create_user(auth_database_session, "family-revoke-other@example.test")
    target_family_id = uuid4()
    other_family_id = uuid4()
    repository = AuthSessionRepository(auth_database_session)
    original_revocation = datetime.now(UTC) - timedelta(minutes=1)
    sessions = {
        "active_one": AuthSession(
            user_id=target_user.id,
            token_digest="family-revoke-active-one",
            family_id=target_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "active_two": AuthSession(
            user_id=target_user.id,
            token_digest="family-revoke-active-two",
            family_id=target_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "already_revoked": AuthSession(
            user_id=target_user.id,
            token_digest="family-revoke-already-revoked",
            family_id=target_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked_at=original_revocation,
        ),
        "expired": AuthSession(
            user_id=target_user.id,
            token_digest="family-revoke-expired",
            family_id=target_family_id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
        "same_user_other_family": AuthSession(
            user_id=target_user.id,
            token_digest="family-revoke-same-user-other-family",
            family_id=other_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "other_user": AuthSession(
            user_id=other_user.id,
            token_digest="family-revoke-other-user",
            family_id=other_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
    }
    for auth_session in sessions.values():
        repository.add(auth_session)
    await auth_database_session.commit()
    token_digests = {name: auth_session.token_digest for name, auth_session in sessions.items()}

    revoked_at = datetime.now(UTC)
    await repository.revoke_family(target_family_id, revoked_at=revoked_at)

    for name in ("active_one", "active_two", "expired"):
        await auth_database_session.refresh(sessions[name])
        stored_revoked_at = sessions[name].revoked_at
        assert stored_revoked_at == revoked_at
        assert stored_revoked_at is not None
        assert stored_revoked_at.tzinfo is not None
    for name in ("already_revoked", "same_user_other_family", "other_user"):
        await auth_database_session.refresh(sessions[name])
    assert sessions["already_revoked"].revoked_at == original_revocation
    assert sessions["same_user_other_family"].revoked_at is None
    assert sessions["other_user"].revoked_at is None

    await auth_database_session.rollback()

    for name in ("active_one", "active_two", "expired"):
        restored = await repository.get_by_token_digest(token_digests[name])
        assert restored is not None
        assert restored.revoked_at is None


@pytest.mark.asyncio
async def test_family_revoke_returns_none_for_an_unknown_family(
    auth_database_session: AsyncSession,
) -> None:
    repository = AuthSessionRepository(auth_database_session)

    await repository.revoke_family(uuid4(), revoked_at=datetime.now(UTC))
