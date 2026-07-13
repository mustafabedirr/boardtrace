import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.models import AuthSession, User
from boardtrace_api.repositories import AuthSessionRepository

pytestmark = [pytest.mark.database, pytest.mark.integration]


async def create_session(
    session: AsyncSession,
    *,
    email: str,
    token_digest: str,
) -> AuthSession:
    user = User(
        email=email,
        normalized_email=email,
        password_hash="argon2-synthetic-hash",
    )
    session.add(user)
    await session.flush()
    auth_session = AuthSession(
        user_id=user.id,
        token_digest=token_digest,
        family_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(auth_session)
    await session.commit()
    return auth_session


async def wait_for_locked_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    token_digest: str,
    started: asyncio.Event,
) -> datetime | None:
    async with sessionmaker() as session:
        repository = AuthSessionRepository(session)
        started.set()
        auth_session = await repository.get_for_update_by_token_digest(token_digest)
        revoked_at = auth_session.revoked_at if auth_session is not None else None
        await session.rollback()
        return revoked_at


@pytest.mark.asyncio
async def test_for_update_lookup_locks_one_row_and_releases_after_commit(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    auth_session = await create_session(
        auth_database_session,
        email="row-lock-commit@example.test",
        token_digest="row-lock-commit",
    )
    await create_session(
        auth_database_session,
        email="row-lock-independent@example.test",
        token_digest="row-lock-independent",
    )
    async with auth_sessionmaker() as transaction_a:
        repository_a = AuthSessionRepository(transaction_a)
        locked_session = await repository_a.get_for_update_by_token_digest("row-lock-commit")
        assert locked_session is not None
        expected_revocation = datetime.now(UTC)
        locked_session.revoked_at = expected_revocation
        await transaction_a.flush()

        waiting_started = asyncio.Event()
        waiting_task = asyncio.create_task(
            wait_for_locked_session(auth_sessionmaker, "row-lock-commit", waiting_started)
        )
        await asyncio.wait_for(waiting_started.wait(), timeout=1)

        async with auth_sessionmaker() as independent_transaction:
            independent_repository = AuthSessionRepository(independent_transaction)
            independent = await asyncio.wait_for(
                independent_repository.get_for_update_by_token_digest("row-lock-independent"),
                timeout=1,
            )
            assert independent is not None
            await independent_transaction.rollback()

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_task), timeout=0.1)

        await transaction_a.commit()

    observed_revocation = await asyncio.wait_for(waiting_task, timeout=1)
    assert observed_revocation == expected_revocation
    assert observed_revocation is not None
    assert observed_revocation.tzinfo is not None
    assert auth_session.id is not None


@pytest.mark.asyncio
async def test_for_update_lookup_releases_after_rollback_without_uncommitted_state(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_session(
        auth_database_session,
        email="row-lock-rollback@example.test",
        token_digest="row-lock-rollback",
    )
    async with auth_sessionmaker() as transaction_a:
        repository_a = AuthSessionRepository(transaction_a)
        locked_session = await repository_a.get_for_update_by_token_digest("row-lock-rollback")
        assert locked_session is not None
        locked_session.revoked_at = datetime.now(UTC)
        await transaction_a.flush()

        waiting_started = asyncio.Event()
        waiting_task = asyncio.create_task(
            wait_for_locked_session(auth_sessionmaker, "row-lock-rollback", waiting_started)
        )
        await asyncio.wait_for(waiting_started.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_task), timeout=0.1)

        await transaction_a.rollback()

    assert await asyncio.wait_for(waiting_task, timeout=1) is None


@pytest.mark.asyncio
async def test_for_update_lookup_returns_none_for_an_unknown_digest(
    auth_database_session: AsyncSession,
) -> None:
    repository = AuthSessionRepository(auth_database_session)

    assert await repository.get_for_update_by_token_digest("unknown-row-lock-digest") is None
