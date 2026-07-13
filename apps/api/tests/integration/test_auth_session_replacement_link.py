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
async def test_replacement_link_persists_overwrites_and_is_commit_free(
    auth_database_session: AsyncSession,
) -> None:
    parent_user = await create_user(auth_database_session, "replacement-parent@example.test")
    other_user = await create_user(auth_database_session, "replacement-other@example.test")
    repository = AuthSessionRepository(auth_database_session)
    parent = AuthSession(
        user_id=parent_user.id,
        token_digest="replacement-parent",
        family_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    same_user_replacement = AuthSession(
        user_id=parent_user.id,
        token_digest="replacement-same-user",
        family_id=parent.family_id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    cross_user_cross_family_replacement = AuthSession(
        user_id=other_user.id,
        token_digest="replacement-cross-user-cross-family",
        family_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    for auth_session in (parent, same_user_replacement, cross_user_cross_family_replacement):
        repository.add(auth_session)
    await auth_database_session.commit()
    same_user_replacement_id = same_user_replacement.id

    await repository.link_replacement(parent, same_user_replacement_id)
    assert parent.replaced_by_session_id == same_user_replacement_id
    await auth_database_session.commit()
    await auth_database_session.refresh(parent)
    assert parent.replaced_by_session_id == same_user_replacement_id

    await repository.link_replacement(parent, cross_user_cross_family_replacement.id)
    assert parent.replaced_by_session_id == cross_user_cross_family_replacement.id
    await auth_database_session.flush()

    await repository.link_replacement(parent, parent.id)
    assert parent.replaced_by_session_id == parent.id
    await auth_database_session.flush()
    await auth_database_session.rollback()

    restored_parent = await repository.get_by_token_digest("replacement-parent")
    assert restored_parent is not None
    assert restored_parent.replaced_by_session_id == same_user_replacement_id


@pytest.mark.asyncio
async def test_replacement_link_enforces_the_replacement_foreign_key(
    auth_database_session: AsyncSession,
) -> None:
    user = await create_user(auth_database_session, "replacement-fk@example.test")
    parent = AuthSession(
        user_id=user.id,
        token_digest="replacement-fk-parent",
        family_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repository = AuthSessionRepository(auth_database_session)
    repository.add(parent)
    await auth_database_session.commit()

    await repository.link_replacement(parent, uuid4())
    with pytest.raises(IntegrityError):
        await auth_database_session.flush()
    await auth_database_session.rollback()

    restored_parent = await repository.get_by_token_digest("replacement-fk-parent")
    assert restored_parent is not None
    assert restored_parent.replaced_by_session_id is None
