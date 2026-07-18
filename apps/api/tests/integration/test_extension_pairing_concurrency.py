import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import ExtensionPairing, User
from boardtrace_api.services.pairing import PairingError, PairingService

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.concurrency]

SETTINGS = Settings(
    jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
    refresh_token_pepper="test-refresh-token-pepper",
)
SCOPES = ("games:ingest", "games:read-status")


async def create_user(session: AsyncSession, email: str) -> User:
    auth = AuthenticationService(session, PasswordService(), TokenService(SETTINGS))
    user, _ = await auth.register(email, "correct-horse-battery-staple", None)
    await session.commit()
    return user


async def create_pairing(session: AsyncSession, user_id: UUID) -> tuple[str, UUID]:
    code, _ = await PairingService(session, SETTINGS).create(user_id, "test-extension", SCOPES)
    await session.commit()
    item = await session.scalar(
        select(ExtensionPairing).where(
            ExtensionPairing.code_digest == TokenService(SETTINGS).digest_refresh_token(code)
        )
    )
    assert item is not None
    return code, item.id


async def exchange(
    sessionmaker: async_sessionmaker[AsyncSession], code: str
) -> tuple[str, str | None]:
    async with sessionmaker() as session:
        try:
            token = await PairingService(session, SETTINGS).exchange(code, "test-extension")
            await session.commit()
            return "success", token
        except PairingError:
            await session.rollback()
            return "rejected", None


async def pairing_by_id(session: AsyncSession, pairing_id: UUID) -> ExtensionPairing:
    session.expire_all()
    pairing = await session.get(ExtensionPairing, pairing_id)
    assert pairing is not None
    return pairing


@pytest.mark.asyncio
async def test_same_code_exchange_consumes_once_and_issues_once(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await create_user(auth_database_session, "pairing-concurrent@example.test")
    user_id = user.id
    code, pairing_id = await create_pairing(auth_database_session, user.id)
    issued = 0
    original = TokenService.issue_extension_token

    def count_issue(
        self: TokenService, user_id: UUID, extension_id: str, scopes: tuple[str, ...]
    ) -> str:
        nonlocal issued
        issued += 1
        return original(self, user_id, extension_id, scopes)

    monkeypatch.setattr(TokenService, "issue_extension_token", count_issue)
    start = asyncio.Event()

    async def run() -> tuple[str, str | None]:
        await start.wait()
        return await exchange(auth_sessionmaker, code)

    first, second = asyncio.create_task(run()), asyncio.create_task(run())
    start.set()
    outcomes = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
    assert [result[0] for result in outcomes].count("success") == 1
    assert [result[0] for result in outcomes].count("rejected") == 1
    assert issued == 1
    pairing = await pairing_by_id(auth_database_session, pairing_id)
    assert pairing.redeemed_at is not None
    assert pairing.user_id == user_id
    assert pairing.scopes == list(SCOPES)


@pytest.mark.asyncio
async def test_rollback_waiter_can_consume_after_lock_release(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(auth_database_session, "pairing-rollback@example.test")
    code, pairing_id = await create_pairing(auth_database_session, user.id)
    digest = TokenService(SETTINGS).digest_refresh_token(code)
    async with auth_sessionmaker() as transaction_a:
        locked = await transaction_a.scalar(
            select(ExtensionPairing).where(ExtensionPairing.code_digest == digest).with_for_update()
        )
        assert locked is not None
        waiter = asyncio.create_task(exchange(auth_sessionmaker, code))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(waiter), timeout=0.1)
        await transaction_a.rollback()
    outcome, token = await asyncio.wait_for(waiter, timeout=2)
    assert outcome == "success"
    assert token is not None
    assert (await pairing_by_id(auth_database_session, pairing_id)).redeemed_at is not None


@pytest.mark.asyncio
async def test_replay_expiry_and_isolation_preserve_other_pairings(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_a = await create_user(auth_database_session, "pairing-a@example.test")
    user_b = await create_user(auth_database_session, "pairing-b@example.test")
    code_a, id_a = await create_pairing(auth_database_session, user_a.id)
    code_other, id_other = await create_pairing(auth_database_session, user_b.id)
    assert (await exchange(auth_sessionmaker, code_a))[0] == "success"
    assert (await exchange(auth_sessionmaker, code_a))[0] == "rejected"
    expired = await pairing_by_id(auth_database_session, id_other)
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_database_session.commit()
    assert (await exchange(auth_sessionmaker, code_other))[0] == "rejected"
    assert (await pairing_by_id(auth_database_session, id_a)).redeemed_at is not None
    assert (await pairing_by_id(auth_database_session, id_other)).redeemed_at is None


@pytest.mark.asyncio
async def test_different_valid_codes_exchange_independently(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(auth_database_session, "pairing-different@example.test")
    first_code, first_id = await create_pairing(auth_database_session, user.id)
    second_code, second_id = await create_pairing(auth_database_session, user.id)
    results = await asyncio.wait_for(
        asyncio.gather(
            exchange(auth_sessionmaker, first_code), exchange(auth_sessionmaker, second_code)
        ),
        timeout=5,
    )
    assert [result[0] for result in results] == ["success", "success"]
    assert (await pairing_by_id(auth_database_session, first_id)).redeemed_at is not None
    assert (await pairing_by_id(auth_database_session, second_id)).redeemed_at is not None


@pytest.mark.asyncio
async def test_concurrent_valid_and_expired_codes_do_not_interfere(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(auth_database_session, "pairing-expiry-matrix@example.test")
    valid_code, valid_id = await create_pairing(auth_database_session, user.id)
    expired_code, expired_id = await create_pairing(auth_database_session, user.id)
    expired = await pairing_by_id(auth_database_session, expired_id)
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_database_session.commit()
    results = await asyncio.wait_for(
        asyncio.gather(
            exchange(auth_sessionmaker, valid_code),
            exchange(auth_sessionmaker, expired_code),
        ),
        timeout=5,
    )
    assert [result[0] for result in results] == ["success", "rejected"]
    assert (await pairing_by_id(auth_database_session, valid_id)).redeemed_at is not None
    assert (await pairing_by_id(auth_database_session, expired_id)).redeemed_at is None


@pytest.mark.asyncio
async def test_token_issuance_failure_rolls_back_the_consume(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await create_user(auth_database_session, "pairing-issuance-failure@example.test")
    code, pairing_id = await create_pairing(auth_database_session, user.id)

    def fail_issue(
        self: TokenService, user_id: UUID, extension_id: str, scopes: tuple[str, ...]
    ) -> str:
        raise RuntimeError("issuer unavailable")

    monkeypatch.setattr(TokenService, "issue_extension_token", fail_issue)
    async with auth_sessionmaker() as session:
        with pytest.raises(RuntimeError, match="issuer unavailable"):
            await PairingService(session, SETTINGS).exchange(code, "test-extension")
        await session.rollback()
    assert (await pairing_by_id(auth_database_session, pairing_id)).redeemed_at is None
    monkeypatch.undo()
    assert (await exchange(auth_sessionmaker, code))[0] == "success"


@pytest.mark.asyncio
async def test_http_same_code_exchange_returns_one_success(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    registration = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "pairing-http@example.com", "password": "correct-horse-battery-staple"},
    )
    assert registration.status_code == 200
    pairing = await auth_client.post(
        "/api/v1/extension-pairings",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
        json={"extension_id": "test-extension", "scopes": list(SCOPES)},
    )
    code = pairing.json()["code"]

    async def request() -> httpx.Response:
        return await auth_client.post(
            "/api/v1/extension-pairings/exchange",
            json={"code": code, "extension_id": "test-extension"},
        )

    responses = await asyncio.wait_for(asyncio.gather(request(), request()), timeout=5)
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert all(response.headers["Cache-Control"] == "no-store" for response in responses)
    assert all(code not in response.text for response in responses)
    digest = TokenService(SETTINGS).digest_refresh_token(code)
    record = await auth_database_session.scalar(
        select(ExtensionPairing).where(ExtensionPairing.code_digest == digest)
    )
    assert record is not None and record.redeemed_at is not None
