from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AuthSession, User
from boardtrace_api.repositories import AuthSessionRepository

pytestmark = [pytest.mark.database, pytest.mark.integration]


@pytest.mark.asyncio
async def test_single_revoke_is_isolated_and_commit_free(
    auth_database_session: AsyncSession,
) -> None:
    user = User(
        email="revoke-user@example.test",
        normalized_email="revoke-user@example.test",
        password_hash="argon2-synthetic-hash",
    )
    auth_database_session.add(user)
    await auth_database_session.flush()
    repository = AuthSessionRepository(auth_database_session)
    sessions = [
        AuthSession(
            user_id=user.id,
            token_digest=f"revoke-synthetic-digest-{number}",
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        for number in range(2)
    ]
    for item in sessions:
        repository.add(item)
    await auth_database_session.flush()

    revoked_at = datetime.now(UTC)
    await repository.revoke(sessions[0], revoked_at=revoked_at)
    assert sessions[0].revoked_at == revoked_at
    assert sessions[1].revoked_at is None
    await auth_database_session.rollback()

    assert await repository.get_by_token_digest("revoke-synthetic-digest-0") is None


@pytest.mark.asyncio
async def test_single_revoke_replaces_the_timestamp_without_affecting_other_user(
    auth_database_session: AsyncSession,
) -> None:
    users = []
    for email in ("first-revoke-user@example.test", "second-revoke-user@example.test"):
        user = User(email=email, normalized_email=email, password_hash="argon2-synthetic-hash")
        auth_database_session.add(user)
        users.append(user)
    await auth_database_session.flush()
    repository = AuthSessionRepository(auth_database_session)
    sessions = []
    for user, digest in zip(users, ("first-revoke-digest", "second-revoke-digest"), strict=True):
        item = AuthSession(
            user_id=user.id,
            token_digest=digest,
            family_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        repository.add(item)
        sessions.append(item)
    await auth_database_session.flush()

    first_time = datetime.now(UTC)
    second_time = first_time + timedelta(seconds=1)
    await repository.revoke(sessions[0], revoked_at=first_time)
    await repository.revoke(sessions[0], revoked_at=second_time)

    assert sessions[0].revoked_at == second_time
    assert sessions[1].revoked_at is None
