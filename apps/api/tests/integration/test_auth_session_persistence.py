from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
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
async def test_auth_session_persists_and_looks_up_digest(
    auth_database_session: AsyncSession,
) -> None:
    user = await create_user(auth_database_session, "session-user@example.test")
    repository = AuthSessionRepository(auth_database_session)
    session = AuthSession(
        user_id=user.id,
        token_digest="synthetic-digest-one",
        family_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repository.add(session)
    await auth_database_session.commit()

    found = await repository.get_by_token_digest("synthetic-digest-one")
    assert found is not None
    assert found.id == session.id
    assert found.created_at.tzinfo is not None
    assert found.expires_at.tzinfo is not None
    assert await repository.get_by_token_digest("unknown-synthetic-digest") is None


@pytest.mark.asyncio
async def test_auth_session_constraints_recover_after_rollback(
    auth_database_session: AsyncSession,
) -> None:
    user = await create_user(auth_database_session, "constraint-user@example.test")
    repository = AuthSessionRepository(auth_database_session)
    for _ in range(2):
        repository.add(
            AuthSession(
                user_id=user.id,
                token_digest="duplicate-synthetic-digest",
                family_id=uuid4(),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
    with pytest.raises(IntegrityError):
        await auth_database_session.flush()
    await auth_database_session.rollback()
    assert await repository.get_by_token_digest("duplicate-synthetic-digest") is None


@pytest.mark.asyncio
async def test_auth_session_persists_expiry_revocation_and_nullable_timestamps(
    auth_database_session: AsyncSession,
) -> None:
    user = await create_user(auth_database_session, "expired-session@example.test")
    repository = AuthSessionRepository(auth_database_session)
    revoked_at = datetime.now(UTC)
    session = AuthSession(
        user_id=user.id,
        token_digest="expired-revoked-synthetic-digest",
        family_id=uuid4(),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        revoked_at=revoked_at,
    )
    repository.add(session)
    await auth_database_session.commit()

    found = await repository.get_by_token_digest("expired-revoked-synthetic-digest")
    assert found is not None
    assert found.revoked_at is not None
    assert found.revoked_at.tzinfo is not None
    assert found.last_used_at is None
    assert found.replaced_by_session_id is None


def test_auth_session_metadata_excludes_raw_token_fields() -> None:
    columns = set(AuthSession.__table__.columns.keys())
    assert "token_digest" in columns
    assert "refresh_token" not in columns
    assert "access_token" not in columns
    assert "authorization" not in columns
