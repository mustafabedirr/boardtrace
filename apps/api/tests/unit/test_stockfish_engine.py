from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event, Lock
from uuid import UUID, uuid4

import chess
import chess.engine
import pytest

from boardtrace_api.analysis.stockfish import (
    EngineExecutionForbidden,
    InvalidEnginePosition,
    PostGameEngineAuthorization,
    StockfishAnalysisRequest,
    StockfishAnalysisTimeout,
    StockfishEngine,
    StockfishExecutionError,
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
        self.quit_calls = 0
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
        self.quit_calls += 1


class ReusableFakeEngine(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.analysis_calls = 0

    def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.InfoDict:
        self.analysis_calls += 1
        move = next(iter(board.legal_moves))
        assert limit.depth is not None
        return {
            "score": chess.engine.PovScore(chess.engine.Cp(self.analysis_calls), board.turn),
            "pv": [move],
            "depth": limit.depth,
        }


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


def _unexpected_launcher(launches: list[str]) -> Callable[[str, float], UciEngine]:
    def launch(path: str, timeout_seconds: float) -> UciEngine:
        launches.append(path)
        assert timeout_seconds == 30.0
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
    engine = StockfishEngine("stockfish", 2, 64, launcher=lambda _path, _timeout: fake)

    result = engine.analyse(authorization, _request(authorization.game_id))

    assert result.score.centipawns == 34
    assert result.score.mate_in is None
    assert result.best_move_uci == "e2e4"
    assert result.principal_variation_uci == ("e2e4", "e7e5")
    assert result.engine_name == "Stockfish"
    assert fake.configured == {"Threads": 2, "Hash": 64}
    assert fake.quit_called is True


def test_analysis_session_reuses_one_process_and_configures_and_stops_once() -> None:
    fake = ReusableFakeEngine()
    launches = 0

    def launch(_path: str, _timeout: float) -> UciEngine:
        nonlocal launches
        launches += 1
        return fake

    authorization = _authorization()
    engine = StockfishEngine("stockfish", 2, 64, launcher=launch)
    first = _request(authorization.game_id)
    second = StockfishAnalysisRequest(
        game_id=authorization.game_id,
        position_id=uuid4(),
        fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        depth=12,
    )

    with engine.analysis_session(authorization) as session:
        first_result = session.analyse(first)
        second_result = session.analyse(second)

    assert launches == 1
    assert fake.configured == {"Threads": 2, "Hash": 64}
    assert fake.analysis_calls == 2
    assert fake.quit_called is True
    assert fake.quit_calls == 1
    assert first_result.position_id == first.position_id
    assert second_result.position_id == second.position_id


def test_engine_requires_a_configured_executable() -> None:
    authorization = _authorization()
    engine = StockfishEngine(None, 1, 64)

    with pytest.raises(StockfishUnavailable):
        engine.analyse(authorization, _request(authorization.game_id))


def test_uci_startup_timeout_is_reported_as_unavailable() -> None:
    authorization = _authorization()

    def launch(_path: str, timeout_seconds: float) -> UciEngine:
        assert timeout_seconds == 0.25
        raise TimeoutError

    engine = StockfishEngine("stockfish", 1, 64, 0.25, launcher=launch)

    with pytest.raises(StockfishUnavailable, match="startup timed out"):
        engine.analyse(authorization, _request(authorization.game_id))


def test_engine_configuration_is_loaded_from_typed_settings() -> None:
    engine = StockfishEngine.from_settings(
        Settings(
            stockfish_path="/opt/stockfish",
            stockfish_threads=2,
            stockfish_hash_mb=96,
            stockfish_timeout_seconds=4.5,
        )
    )

    assert engine._executable_path == "/opt/stockfish"
    assert engine._threads == 2
    assert engine._hash_mb == 96
    assert engine._timeout_seconds == 4.5


@pytest.mark.parametrize(
    ("status", "verified", "allowed"),
    [
        (GameStatus.CREATED, True, False),
        (GameStatus.CAPTURING, True, False),
        (GameStatus.FINISH_PENDING, True, False),
        (GameStatus.FINISHED, False, False),
        (GameStatus.FINISHED, True, True),
        (GameStatus.DEEP_ANALYSIS_RUNNING, False, False),
        (GameStatus.DEEP_ANALYSIS_RUNNING, True, True),
        (GameStatus.ANALYSIS_AVAILABLE, True, False),
        (GameStatus.FAILED, True, False),
    ],
)
def test_engine_eligibility_matches_domain_state_contract(
    status: GameStatus, verified: bool, allowed: bool
) -> None:
    launches: list[str] = []
    fake = FakeEngine()
    authorization = PostGameEngineAuthorization(
        uuid4(), status, datetime.now(UTC) if verified else None
    )

    def launch(path: str, timeout_seconds: float) -> UciEngine:
        launches.append(path)
        assert timeout_seconds == 3.0
        return fake

    engine = StockfishEngine("stockfish", 1, 64, 3.0, launcher=launch)
    if allowed:
        engine.analyse(authorization, _request(authorization.game_id))
        assert launches == ["stockfish"]
    else:
        with pytest.raises(EngineExecutionForbidden):
            engine.analyse(authorization, _request(authorization.game_id))
        assert launches == []


class FailingEngine(FakeEngine):
    def __init__(self, failure: BaseException, quit_failure: BaseException | None = None) -> None:
        super().__init__()
        self._failure = failure
        self._quit_failure = quit_failure

    def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.InfoDict:
        raise self._failure

    def quit(self) -> None:
        self.quit_called = True
        self.quit_calls += 1
        if self._quit_failure is not None:
            raise self._quit_failure


def test_analysis_timeout_invalidates_process_and_next_request_starts_fresh() -> None:
    timed_out = FailingEngine(TimeoutError(), TimeoutError())
    healthy = FakeEngine()
    launched: list[UciEngine] = []

    def launch(_path: str, _timeout: float) -> UciEngine:
        instance: UciEngine = timed_out if not launched else healthy
        launched.append(instance)
        return instance

    authorization = _authorization()
    engine = StockfishEngine("stockfish", 1, 64, launcher=launch)

    with pytest.raises(StockfishAnalysisTimeout):
        engine.analyse(authorization, _request(authorization.game_id))
    result = engine.analyse(authorization, _request(authorization.game_id))

    assert result.best_move_uci == "e2e4"
    assert timed_out.quit_called is True
    assert timed_out.quit_calls == 1
    assert healthy.quit_called is True
    assert launched == [timed_out, healthy]


def test_crashed_process_is_cleaned_up_without_masking_failure() -> None:
    crashed = FailingEngine(
        chess.engine.EngineTerminatedError("crashed"),
        chess.engine.EngineTerminatedError("already stopped"),
    )
    authorization = _authorization()
    engine = StockfishEngine("stockfish", 1, 64, launcher=lambda _path, _timeout: crashed)

    with pytest.raises(StockfishExecutionError, match="analysis failed"):
        engine.analyse(authorization, _request(authorization.game_id))

    assert crashed.quit_called is True
    assert crashed.quit_calls == 1


def test_cancellation_is_re_raised_after_cleanup() -> None:
    cancelled = FailingEngine(KeyboardInterrupt())
    authorization = _authorization()
    engine = StockfishEngine("stockfish", 1, 64, launcher=lambda _path, _timeout: cancelled)

    with pytest.raises(KeyboardInterrupt):
        engine.analyse(authorization, _request(authorization.game_id))

    assert cancelled.quit_called is True
    assert cancelled.quit_calls == 1


def test_concurrent_requests_are_serialized_and_use_fresh_processes() -> None:
    barrier = Barrier(3)
    release_first = Event()
    state_lock = Lock()
    active = 0
    maximum_active = 0
    engines: list[FakeEngine] = []

    class BlockingEngine(FakeEngine):
        def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.InfoDict:
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
                first = len(engines) == 1
            try:
                if first:
                    assert release_first.wait(timeout=2)
                return super().analyse(board, limit)
            finally:
                with state_lock:
                    active -= 1

    def launch(_path: str, _timeout: float) -> UciEngine:
        instance = BlockingEngine()
        engines.append(instance)
        return instance

    authorization = _authorization()
    engine = StockfishEngine("stockfish", 1, 64, launcher=launch)

    def analyse() -> None:
        barrier.wait()
        engine.analyse(authorization, _request(authorization.game_id))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(analyse) for _ in range(2)]
        barrier.wait()
        while not engines:
            pass
        release_first.set()
        for future in futures:
            future.result(timeout=3)

    assert maximum_active == 1
    assert len(engines) == 2
    assert all(instance.quit_called for instance in engines)


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
