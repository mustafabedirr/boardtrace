import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationError, AuthenticationService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import AuthSession
from boardtrace_api.repositories import AuthSessionRepository

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


async def refresh_in_separate_transaction(
    sessionmaker: async_sessionmaker[AsyncSession],
    raw_refresh_token: str,
    started: asyncio.Event,
) -> tuple[str, str | None]:
    async with sessionmaker() as session:
        service, _ = create_service(session)
        started.set()
        try:
            pair = await service.refresh(raw_refresh_token)
        except AuthenticationError:
            await session.commit()
            return "rejected", None
        await session.commit()
        return "success", pair.refresh_token


@pytest.mark.asyncio
async def test_concurrent_refresh_allows_one_rotation_then_compromises_its_family(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    seed_service, tokens = create_service(auth_database_session)
    user, root_pair = await seed_service.register(
        "concurrent-refresh@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user_id = user.id
    same_user_other_family_pair = await seed_service.login(
        "concurrent-refresh@example.test",
        "correct-horse-battery-staple",
    )
    await auth_database_session.commit()
    _, other_user_pair = await seed_service.register(
        "concurrent-refresh-other@example.test",
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

    async with auth_sessionmaker() as transaction_a:
        service_a, _ = create_service(transaction_a)
        locked_parent = await AuthSessionRepository(transaction_a).get_for_update_by_token_digest(
            root_digest
        )
        assert locked_parent is not None
        waiting_started = asyncio.Event()
        waiting_refresh = asyncio.create_task(
            refresh_in_separate_transaction(
                auth_sessionmaker,
                root_pair.refresh_token,
                waiting_started,
            )
        )
        await asyncio.wait_for(waiting_started.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_refresh), timeout=0.1)

        first_pair = await service_a.refresh(root_pair.refresh_token)
        await transaction_a.commit()

    outcome, second_refresh_token = await asyncio.wait_for(waiting_refresh, timeout=1)
    assert outcome == "rejected"
    assert second_refresh_token is None

    auth_database_session.expire_all()
    family_sessions = list(
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
    first_replacement_digest = tokens.digest_refresh_token(first_pair.refresh_token)
    assert len(family_sessions) == 2
    assert any(
        auth_session.token_digest == first_replacement_digest for auth_session in family_sessions
    )
    assert all(auth_session.revoked_at is not None for auth_session in family_sessions)
    assert same_user_other_family is not None
    assert same_user_other_family.user_id == user_id
    assert same_user_other_family.revoked_at is None
    assert other_user_session is not None
    assert other_user_session.user_id != user_id
    assert other_user_session.revoked_at is None


@pytest.mark.asyncio
async def test_concurrent_refresh_waiter_rotates_after_the_lock_owner_rolls_back(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    seed_service, tokens = create_service(auth_database_session)
    user, root_pair = await seed_service.register(
        "concurrent-refresh-rollback@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user_id = user.id
    root_digest = tokens.digest_refresh_token(root_pair.refresh_token)

    async with auth_sessionmaker() as transaction_a:
        locked_parent = await AuthSessionRepository(transaction_a).get_for_update_by_token_digest(
            root_digest
        )
        assert locked_parent is not None
        waiting_started = asyncio.Event()
        waiting_refresh = asyncio.create_task(
            refresh_in_separate_transaction(
                auth_sessionmaker,
                root_pair.refresh_token,
                waiting_started,
            )
        )
        await asyncio.wait_for(waiting_started.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiting_refresh), timeout=0.1)
        await transaction_a.rollback()

    outcome, replacement_token = await asyncio.wait_for(waiting_refresh, timeout=1)
    assert outcome == "success"
    assert replacement_token is not None
    auth_database_session.expire_all()
    sessions = list(
        (
            await auth_database_session.scalars(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).all()
    )
    replacement_digest = tokens.digest_refresh_token(replacement_token)
    assert len(sessions) == 2
    assert any(auth_session.token_digest == replacement_digest for auth_session in sessions)
    assert sum(auth_session.revoked_at is None for auth_session in sessions) == 1
