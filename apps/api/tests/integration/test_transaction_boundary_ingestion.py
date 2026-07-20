import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import PostgresDsn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.app import create_app
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.db.transactions import get_before_commit_hook
from boardtrace_api.ingestion_observability import (
    IngestionTerminalObserver,
    IngestionTerminalOutcome,
    get_ingestion_terminal_observer,
)
from boardtrace_api.models import AnalysisJob, Game, User
from tests.postgres_helpers import get_test_database_url

pytestmark = [pytest.mark.database, pytest.mark.integration]


class InjectedBeforeCommitFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordedTerminalEvent:
    outcome: IngestionTerminalOutcome
    operation: str
    game_id: UUID | None
    error_type: str | None


class RecordingIngestionTerminalObserver:
    def __init__(self) -> None:
        self.events: list[RecordedTerminalEvent] = []

    async def record_terminal_outcome(
        self,
        *,
        outcome: IngestionTerminalOutcome,
        operation: str,
        game_id: UUID | None,
        error_type: str | None,
    ) -> None:
        self.events.append(RecordedTerminalEvent(outcome, operation, game_id, error_type))


class RecordingObserverProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.observer = RecordingIngestionTerminalObserver()

    def __call__(self) -> IngestionTerminalObserver:
        self.calls += 1
        return self.observer


def settings() -> Settings:
    return Settings(
        database_url=PostgresDsn(get_test_database_url()),
        jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
        refresh_token_pepper="test-refresh-token-pepper",
    )


async def extension_token(session: AsyncSession, resolved: Settings) -> str:
    user = User(
        email=f"transaction-{uuid4()}@example.com",
        normalized_email=f"transaction-{uuid4()}@example.com",
        display_name=None,
        password_hash=None,
    )
    session.add(user)
    await session.commit()
    return TokenService(resolved).issue_extension_token(
        user.id, "transaction-test", ("games:ingest",)
    )


def payload() -> dict[str, object]:
    return {
        "idempotency_key": hashlib.sha256(uuid4().bytes).hexdigest(),
        "platform": "lichess",
        "source_game_id": str(uuid4()),
        "completed_at": "2026-07-20T10:00:00Z",
        "player_color": "UNKNOWN",
        "result": "UNKNOWN",
        "initial_fen": None,
        "moves": ["e2e4"],
    }


@pytest.mark.asyncio
async def test_failing_before_commit_hook_rolls_back_ingestion_durably(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    resolved = settings()
    app = create_app(resolved)
    observer_provider = RecordingObserverProvider()

    async def failing_hook() -> None:
        raise InjectedBeforeCommitFailure("injected pre-commit failure")

    app.dependency_overrides[get_before_commit_hook] = lambda: failing_hook
    app.dependency_overrides[get_ingestion_terminal_observer] = observer_provider
    try:
        token = await extension_token(auth_database_session, resolved)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with pytest.raises(InjectedBeforeCommitFailure):
                await client.post(
                    "/api/v1/games/ingestions",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload(),
                )
        assert observer_provider.observer.events == [
            RecordedTerminalEvent(
                IngestionTerminalOutcome.FAILURE,
                "completed_game_ingestion",
                None,
                "InjectedBeforeCommitFailure",
            )
        ]
        async with auth_sessionmaker() as verification_session:
            assert await verification_session.scalar(select(func.count(Game.id))) == 0
            assert await verification_session.scalar(select(func.count(AnalysisJob.id))) == 0
    finally:
        app.dependency_overrides.clear()
        assert get_before_commit_hook not in app.dependency_overrides
        assert get_ingestion_terminal_observer not in app.dependency_overrides
        await app.state.database_engine.dispose()


@pytest.mark.asyncio
async def test_no_op_before_commit_hook_durably_commits_ingestion(
    auth_database_session: AsyncSession,
    auth_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    resolved = settings()
    app = create_app(resolved)
    observer_provider = RecordingObserverProvider()
    app.dependency_overrides[get_ingestion_terminal_observer] = observer_provider
    try:
        token = await extension_token(auth_database_session, resolved)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {token}"},
                json=payload(),
            )
        assert response.status_code == 201
        assert response.json()["analysis_available"] is False
        event = observer_provider.observer.events
        assert len(event) == 1
        assert event[0].outcome is IngestionTerminalOutcome.SUCCESS
        assert event[0].operation == "completed_game_ingestion"
        assert event[0].game_id is not None
        assert event[0].error_type is None
        async with auth_sessionmaker() as verification_session:
            assert await verification_session.scalar(select(func.count(Game.id))) == 1
            assert await verification_session.scalar(select(func.count(AnalysisJob.id))) == 1
    finally:
        app.dependency_overrides.clear()
        assert get_ingestion_terminal_observer not in app.dependency_overrides
        await app.state.database_engine.dispose()


@pytest.mark.asyncio
async def test_ingestion_endpoint_resolves_overridden_terminal_observer(
    auth_database_session: AsyncSession,
) -> None:
    resolved = settings()
    app = create_app(resolved)
    observer_provider = RecordingObserverProvider()
    app.dependency_overrides[get_ingestion_terminal_observer] = observer_provider
    try:
        token = await extension_token(auth_database_session, resolved)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/games/ingestions",
                headers={"Authorization": f"Bearer {token}"},
                json=payload(),
            )
        assert response.status_code == 201
        assert observer_provider.calls == 1
        assert len(observer_provider.observer.events) == 1
        assert observer_provider.observer.events[0].outcome is IngestionTerminalOutcome.SUCCESS
    finally:
        app.dependency_overrides.clear()
        assert get_ingestion_terminal_observer not in app.dependency_overrides
        await app.state.database_engine.dispose()
