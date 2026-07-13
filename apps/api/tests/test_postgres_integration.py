from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings
from boardtrace_api.models import EngineVersion, Game, GameFrame, ModelVersion, Position, User
from boardtrace_api.models.enums import (
    GameResult,
    GameStatus,
    PlayerColor,
    PositionValidationStatus,
)
from boardtrace_api.repositories import GameRepository, PositionRepository, UserRepository
from tests.postgres_helpers import create_test_engine, get_test_database_url

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest_asyncio.fixture
async def database_session() -> AsyncIterator[AsyncSession]:
    engine = create_test_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("TRUNCATE TABLE users CASCADE"))
        await session.commit()
        yield session
    await engine.dispose()


def new_game(user_id: object) -> Game:
    return Game(
        user_id=user_id,
        status=GameStatus.CREATED,
        platform="test-platform",
        player_color=PlayerColor.UNKNOWN,
        result=GameResult.UNKNOWN,
    )


@pytest.mark.asyncio
async def test_repositories_constraints_jsonb_and_cascade(database_session: AsyncSession) -> None:
    users = UserRepository(database_session)
    games = GameRepository(database_session)
    positions = PositionRepository(database_session)
    user = User(
        email="postgres-user@example.test",
        normalized_email="postgres-user@example.test",
    )
    users.add(user)
    await database_session.flush()
    game = new_game(user.id)
    games.add(game)
    await database_session.flush()
    frame = GameFrame(
        game_id=game.id,
        sequence=1,
        captured_at=datetime.now(UTC),
        width=640,
        height=640,
        mime_type="image/png",
        storage_key="captures/scoped-board.png",
    )
    database_session.add(frame)
    await database_session.flush()
    position = Position(
        game_id=game.id,
        frame_id=frame.id,
        ply=1,
        piece_placement="8/8/8/8/8/8/8/8",
        detection_confidence=0.8,
        validation_status=PositionValidationStatus.VALID,
    )
    positions.add(position)
    database_session.add(
        ModelVersion(
            name="board-detector",
            version="1",
            artifact_uri="models/board-detector.onnx",
            checksum="abc",
            framework="onnx",
            metadata_={"nested": {"labels": ["white", "black"]}, "locale": "Türkçe"},
        )
    )
    database_session.add(
        EngineVersion(
            name="stockfish",
            version="test-only-metadata",
            binary_checksum="def",
            configuration={"threads": 1, "options": []},
        )
    )
    await database_session.commit()

    assert await users.get_by_email(user.email) is not None
    assert [item.id for item in await games.get_for_user(user.id)] == [game.id]
    assert [item.id for item in await positions.get_for_game(game.id)] == [position.id]
    metadata = await database_session.scalar(text("SELECT metadata FROM model_versions"))
    assert metadata == {"nested": {"labels": ["white", "black"]}, "locale": "Türkçe"}

    database_session.add(
        Position(
            game_id=game.id,
            ply=1,
            piece_placement="8/8/8/8/8/8/8/8",
            detection_confidence=1.1,
            validation_status=PositionValidationStatus.VALID,
        )
    )
    with pytest.raises(IntegrityError):
        await database_session.commit()
    await database_session.rollback()

    await database_session.delete(game)
    await database_session.commit()
    assert await database_session.scalar(text("SELECT count(*) FROM game_frames")) == 0
    assert await database_session.scalar(text("SELECT count(*) FROM positions")) == 0


@pytest.mark.asyncio
async def test_database_readiness_positive_and_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDTRACE_DATABASE_URL", get_test_database_url())
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        live = await client.get("/api/v1/health/live")
        ready = await client.get("/api/v1/health/ready")
    await app.state.database_engine.dispose()

    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "checks": {"application": "ok", "database": "ok"}}
    assert ready.headers["X-Request-ID"]
    assert "postgresql" not in ready.text.lower()

    monkeypatch.setenv(
        "BOARDTRACE_DATABASE_URL",
        "postgresql+asyncpg://boardtrace:boardtrace@127.0.0.1:55431/unreachable",
    )
    unavailable_app = create_app(Settings())
    unavailable_transport = httpx.ASGITransport(app=unavailable_app)
    async with httpx.AsyncClient(
        transport=unavailable_transport, base_url="http://testserver"
    ) as client:
        unavailable_live = await client.get("/api/v1/health/live")
        unavailable_ready = await client.get("/api/v1/health/ready")
    await unavailable_app.state.database_engine.dispose()

    assert unavailable_live.status_code == 200
    assert unavailable_ready.status_code == 503
    assert unavailable_ready.headers["X-Request-ID"]
    assert "postgresql" not in unavailable_ready.text.lower()
    assert "asyncpg" not in unavailable_ready.text.lower()
