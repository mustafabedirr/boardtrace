from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import User
from boardtrace_api.repositories import UserRepository

pytestmark = [pytest.mark.database, pytest.mark.integration]


@pytest.mark.asyncio
async def test_user_repository_persists_lookups_and_last_login(
    auth_database_session: AsyncSession,
) -> None:
    repository = UserRepository(auth_database_session)
    user = User(
        email="repository-user@example.test",
        normalized_email="repository-user@example.test",
        password_hash="argon2-synthetic-hash",
        is_active=False,
        email_verified=True,
    )
    repository.add(user)
    await auth_database_session.flush()

    assert await repository.get_by_id(user.id) is user
    assert await repository.get_by_email(user.normalized_email) is user
    occurred_at = datetime.now(UTC)
    assert await repository.update_last_login(user.id, occurred_at=occurred_at)
    assert not await repository.update_last_login(uuid4(), occurred_at=occurred_at)
    await auth_database_session.commit()

    assert user.last_login_at is not None
    assert user.last_login_at.tzinfo is not None
    assert not user.is_active
    assert user.email_verified


@pytest.mark.asyncio
async def test_user_repository_unique_email_recovers_after_rollback(
    auth_database_session: AsyncSession,
) -> None:
    repository = UserRepository(auth_database_session)
    for email in ("duplicate@example.test", "duplicate@example.test"):
        repository.add(
            User(
                email=email,
                normalized_email=email,
                password_hash="argon2-synthetic-hash",
            )
        )
    with pytest.raises(IntegrityError):
        await auth_database_session.flush()
    await auth_database_session.rollback()
    assert await repository.get_by_email("duplicate@example.test") is None
