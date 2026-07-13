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
async def test_user_wide_revoke_isolated_includes_expired_sessions_and_is_commit_free(
    auth_database_session: AsyncSession,
) -> None:
    target_user = await create_user(auth_database_session, "bulk-revoke-target@example.test")
    other_user = await create_user(auth_database_session, "bulk-revoke-other@example.test")
    repository = AuthSessionRepository(auth_database_session)
    original_revocation = datetime.now(UTC) - timedelta(minutes=1)
    sessions = {
        "active_one": AuthSession(
            user_id=target_user.id,
            token_digest="bulk-revoke-active-one",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "active_two": AuthSession(
            user_id=target_user.id,
            token_digest="bulk-revoke-active-two",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "already_revoked": AuthSession(
            user_id=target_user.id,
            token_digest="bulk-revoke-already-revoked",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked_at=original_revocation,
        ),
        "expired": AuthSession(
            user_id=target_user.id,
            token_digest="bulk-revoke-expired",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
        "other_user": AuthSession(
            user_id=other_user.id,
            token_digest="bulk-revoke-other-user",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
    }
    for auth_session in sessions.values():
        repository.add(auth_session)
    await auth_database_session.commit()
    token_digests = {name: auth_session.token_digest for name, auth_session in sessions.items()}

    started_at = datetime.now(UTC)
    await repository.revoke_all_for_user(target_user.id)
    finished_at = datetime.now(UTC)

    for name in ("active_one", "active_two", "expired"):
        await auth_database_session.refresh(sessions[name])
        revoked_at = sessions[name].revoked_at
        assert revoked_at is not None
        assert revoked_at.tzinfo is not None
        assert started_at <= revoked_at <= finished_at
    await auth_database_session.refresh(sessions["already_revoked"])
    await auth_database_session.refresh(sessions["other_user"])
    assert sessions["already_revoked"].revoked_at == original_revocation
    assert sessions["other_user"].revoked_at is None

    await auth_database_session.rollback()

    for name in ("active_one", "active_two", "expired"):
        restored = await repository.get_by_token_digest(token_digests[name])
        assert restored is not None
        assert restored.revoked_at is None
    restored_already_revoked = await repository.get_by_token_digest(
        token_digests["already_revoked"]
    )
    assert restored_already_revoked is not None
    assert restored_already_revoked.revoked_at == original_revocation


@pytest.mark.asyncio
async def test_user_wide_revoke_returns_none_when_the_user_has_no_sessions(
    auth_database_session: AsyncSession,
) -> None:
    user = await create_user(auth_database_session, "bulk-revoke-empty@example.test")
    await auth_database_session.commit()
    repository = AuthSessionRepository(auth_database_session)

    await repository.revoke_all_for_user(user.id)
