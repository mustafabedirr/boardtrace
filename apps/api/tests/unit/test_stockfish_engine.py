from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import chess
import chess.engine
import pytest

from boardtrace_api.analysis.stockfish import (
    EngineExecutionForbidden,
    InvalidEnginePosition,
    PostGameEngineAuthorization,
    StockfishAnalysisRequest,
    StockfishEngine,
    StockfishUnavailable,
    UciEngine,
)
from boardtrace_api.app import create_app
from boardtrace_api.config import Settings
from boardtrace_api.models.enums import GameStatus


class FakeEngine:
    def __init__(self) -> None:
        self.configured: dict[str, chess.engine.ConfigValue] | None = None
        self.quit_called = False
        self.id = {"name": "Stockfish", "version": "test"}

    def configure(self, options: object) -> None:
        assert isinstance(options, dict)
        self.configured = options

    def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.InfoDict:
        assert board.turn is chess.WHITE
        assert limit.depth == 12
        return {
            "score": chess.engine.PovScore(chess.engine.Cp(34), chess.WHITE),
            "pv": [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
            "depth": 12,
            "nodes": 123,
            "time": 0.25,
        }

    def quit(self) -> None:
        self.quit_called = True


def _authorization(status: GameStatus = GameStatus.FINISHED) -> PostGameEngineAuthorization:
    return PostGameEngineAuthorization(
        game_id=uuid4(), game_status=status, completion_verified_at=datetime.now(UTC)
    )


def _request(game_id: UUID) -> StockfishAnalysisRequest:
    return StockfishAnalysisRequest(
        game_id=game_id,
        position_id=uuid4(),
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        depth=12,
    )


def _unexpected_launcher(launches: list[str]) -> Callable[[str], UciEngine]:
    def launch(path: str) -> UciEngine:
        launches.append(path)
        raise AssertionError("the engine launcher must not run")

    return launch


@pytest.mark.parametrize(
    "status",
    [
        GameStatus.CREATED,
        GameStatus.CAPTURING,
        GameStatus.FINISH_PENDING,
        GameStatus.FAILED,
        GameStatus.ANALYSIS_AVAILABLE,
    ],
)
def test_engine_is_not_started_for_an_ineligible_game(status: GameStatus) -> None:
    launches: list[str] = []
    engine = StockfishEngine("stockfish", 2, 64, launcher=_unexpected_launcher(launches))
    authorization = _authorization(status)

    with pytest.raises(EngineExecutionForbidden):
        engine.analyse(authorization, _request(authorization.game_id))

    assert launches == []


def test_engine_rejects_unverified_finished_game_before_launch() -> None:
    launches: list[str] = []
    authorization = PostGameEngineAuthorization(uuid4(), GameStatus.FINISHED, None)
    engine = StockfishEngine("stockfish", 1, 64, launcher=_unexpected_launcher(launches))

    with pytest.raises(EngineExecutionForbidden):
        engine.analyse(authorization, _request(authorization.game_id))

    assert launches == []


def test_engine_rejects_authorization_for_a_different_game_before_launch() -> None:
    launches: list[str] = []
    authorization = _authorization()
    engine = StockfishEngine("stockfish", 1, 64, launcher=_unexpected_launcher(launches))

    with pytest.raises(EngineExecutionForbidden):
        engine.analyse(authorization, _request(uuid4()))

    assert launches == []


def test_engine_rejects_invalid_position_before_launch() -> None:
    launches: list[str] = []
    authorization = _authorization()
    invalid_request = StockfishAnalysisRequest(
        game_id=authorization.game_id, position_id=uuid4(), fen="not-a-fen", depth=12
    )
    engine = StockfishEngine("stockfish", 1, 64, launcher=_unexpected_launcher(launches))

    with pytest.raises(InvalidEnginePosition):
        engine.analyse(authorization, invalid_request)

    assert launches == []


def test_engine_returns_typed_internal_result_and_always_stops_process() -> None:
    fake = FakeEngine()
    authorization = _authorization()
    engine = StockfishEngine("stockfish", 2, 64, launcher=lambda _: fake)

    result = engine.analyse(authorization, _request(authorization.game_id))

    assert result.score.centipawns == 34
    assert result.score.mate_in is None
    assert result.best_move_uci == "e2e4"
    assert result.principal_variation_uci == ("e2e4", "e7e5")
    assert result.engine_name == "Stockfish"
    assert fake.configured == {"Threads": 2, "Hash": 64}
    assert fake.quit_called is True


def test_engine_requires_a_configured_executable() -> None:
    authorization = _authorization()
    engine = StockfishEngine(None, 1, 64)

    with pytest.raises(StockfishUnavailable):
        engine.analyse(authorization, _request(authorization.game_id))


def test_engine_configuration_is_loaded_from_typed_settings() -> None:
    engine = StockfishEngine.from_settings(
        Settings(stockfish_path="/opt/stockfish", stockfish_threads=2, stockfish_hash_mb=96)
    )

    assert engine._executable_path == "/opt/stockfish"
    assert engine._threads == 2
    assert engine._hash_mb == 96


def test_internal_engine_result_types_are_absent_from_public_openapi() -> None:
    schema = create_app(Settings()).openapi()
    serialized = str(schema["components"]["schemas"])

    for forbidden_field in (
        "best_move_uci",
        "centipawns",
        "mate_in",
        "principal_variation_uci",
        "engine_version",
    ):
        assert forbidden_field not in serialized
