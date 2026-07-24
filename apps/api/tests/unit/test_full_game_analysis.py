from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import chess
import pytest
from pydantic import ValidationError

from boardtrace_api.analysis.full_game import (
    CompletedGameAnalysisInput,
    EngineReusePolicy,
    FullGameAnalysisBudget,
    FullGameAnalysisFailed,
    FullGameAnalysisStatus,
    FullGameAnalyzer,
    FullGameFailureCode,
    FullGameInputError,
)
from boardtrace_api.analysis.stockfish import (
    PostGameEngineAuthorization,
    StockfishAnalysisRequest,
    StockfishAnalysisResult,
    StockfishScore,
)
from boardtrace_api.app import create_app
from boardtrace_api.config import Settings
from boardtrace_api.models.enums import GameStatus


class RecordingPositionEngine:
    def __init__(
        self, fail_on_call: int | None = None, failure: BaseException | None = None
    ) -> None:
        self.requests: list[StockfishAnalysisRequest] = []
        self.fail_on_call = fail_on_call
        self.failure = failure or RuntimeError("engine failed")
        self.sessions_opened = 0
        self.sessions_closed = 0

    @contextmanager
    def analysis_session(
        self, authorization: PostGameEngineAuthorization
    ) -> Iterator["RecordingPositionEngine"]:
        authorization.require_execution_allowed()
        self.sessions_opened += 1
        try:
            yield self
        finally:
            self.sessions_closed += 1

    def analyse(
        self,
        request: StockfishAnalysisRequest,
    ) -> StockfishAnalysisResult:
        self.requests.append(request)
        if self.fail_on_call == len(self.requests):
            raise self.failure
        board = chess.Board(request.fen)
        best_move = next(iter(board.legal_moves)).uci()
        return StockfishAnalysisResult(
            game_id=request.game_id,
            position_id=request.position_id,
            score=StockfishScore(centipawns=request.depth + len(self.requests)),
            best_move_uci=best_move,
            principal_variation_uci=(best_move,),
            depth=request.depth,
            nodes=100 + len(self.requests),
            time_ms=request.time_limit_ms,
            engine_name="DeterministicEngine",
            engine_version="test",
        )


def _game(
    moves: tuple[str, ...] = ("e2e4", "e7e5", "g1f3"),
    status: GameStatus = GameStatus.FINISHED,
    verified: bool = True,
) -> CompletedGameAnalysisInput:
    return CompletedGameAnalysisInput(
        game_id=uuid4(),
        game_status=status,
        completion_verified_at=datetime.now(UTC) if verified else None,
        initial_fen=None,
        normalized_moves_uci=moves,
    )


def _budget(**overrides: int) -> FullGameAnalysisBudget:
    values = {
        "depth": 8,
        "max_position_time_ms": 500,
        "max_moves": 20,
        "max_positions": 21,
        "max_game_time_ms": 5_000,
    }
    values.update(overrides)
    return FullGameAnalysisBudget(**values)


def test_replays_deterministically_and_evaluates_each_unique_position_once() -> None:
    game = _game()
    engine = RecordingPositionEngine()

    result = FullGameAnalyzer(engine, clock=lambda: 0.0).analyse(game, _budget())

    assert result.status is FullGameAnalysisStatus.COMPLETE
    assert result.engine_reuse_policy is EngineReusePolicy.SINGLE_PROCESS_PER_GAME
    assert engine.sessions_opened == 1
    assert engine.sessions_closed == 1
    assert len(engine.requests) == 4
    assert len(result.move_evaluations) == 3
    assert [record.move_uci for record in result.move_evaluations] == ["e2e4", "e7e5", "g1f3"]
    assert [record.move_san for record in result.move_evaluations] == ["e4", "e5", "Nf3"]
    assert result.move_evaluations[0].after is result.move_evaluations[1].before
    assert result.move_evaluations[1].after is result.move_evaluations[2].before
    assert result.checkpoint.completed_moves == 3
    assert result.checkpoint.evaluated_positions == 4
    assert result.checkpoint.last_evaluated_ply == 3
    assert all(request.time_limit_ms == 500 for request in engine.requests)

    repeated_engine = RecordingPositionEngine()
    repeated = FullGameAnalyzer(repeated_engine, clock=lambda: 0.0).analyse(game, _budget())
    assert [request.position_id for request in repeated_engine.requests] == [
        request.position_id for request in engine.requests
    ]
    assert repeated.move_evaluations == result.move_evaluations
    assert repeated_engine.sessions_opened == 1
    assert repeated_engine.sessions_closed == 1


def test_initial_fen_is_replayed_as_the_server_authoritative_start() -> None:
    game = CompletedGameAnalysisInput(
        game_id=uuid4(),
        game_status=GameStatus.FINISHED,
        completion_verified_at=datetime.now(UTC),
        initial_fen="8/8/8/8/8/8/4K3/6k1 w - - 0 1",
        normalized_moves_uci=("e2e3",),
    )
    engine = RecordingPositionEngine()

    result = FullGameAnalyzer(engine, clock=lambda: 0.0).analyse(game, _budget())

    assert result.move_evaluations[0].before.fen.startswith("8/8/8/8/8/8/4K3/6k1 w")
    assert result.move_evaluations[0].after.fen.startswith("8/8/8/8/8/4K3/8/6k1 b")


@pytest.mark.parametrize(
    "game",
    [
        _game(status=GameStatus.CAPTURING),
        _game(verified=False),
        _game(moves=()),
        _game(moves=("e2e5",)),
        CompletedGameAnalysisInput(
            uuid4(), GameStatus.FINISHED, datetime.now(UTC), "invalid", ("e2e4",)
        ),
    ],
)
def test_invalid_or_ineligible_input_fails_before_engine_execution(
    game: CompletedGameAnalysisInput,
) -> None:
    engine = RecordingPositionEngine()

    with pytest.raises(FullGameInputError):
        FullGameAnalyzer(engine).analyse(game, _budget())

    assert engine.requests == []
    assert engine.sessions_opened == 0


@pytest.mark.parametrize(
    "budget",
    [_budget(max_moves=2), _budget(max_positions=3)],
)
def test_replay_size_budgets_fail_before_engine_execution(
    budget: FullGameAnalysisBudget,
) -> None:
    engine = RecordingPositionEngine()

    with pytest.raises(FullGameInputError):
        FullGameAnalyzer(engine).analyse(_game(), budget)

    assert engine.requests == []
    assert engine.sessions_opened == 0


def test_engine_failure_exposes_only_safely_completed_moves() -> None:
    engine = RecordingPositionEngine(fail_on_call=3)

    with pytest.raises(FullGameAnalysisFailed) as raised:
        FullGameAnalyzer(engine, clock=lambda: 0.0).analyse(_game(), _budget())

    partial = raised.value.partial_result
    assert partial.status is FullGameAnalysisStatus.PARTIAL
    assert [move.move_uci for move in partial.move_evaluations] == ["e2e4"]
    assert partial.checkpoint.evaluated_positions == 2
    assert partial.checkpoint.completed_moves == 1
    assert partial.failure is not None
    assert partial.failure.code is FullGameFailureCode.ENGINE_EXECUTION_FAILED
    assert partial.failure.failed_position_ply == 2
    assert partial.failure.error_type == "RuntimeError"
    assert engine.sessions_opened == 1
    assert engine.sessions_closed == 1


def test_game_deadline_bounds_each_request_and_returns_typed_partial_result() -> None:
    clock_values = iter((0.0, 0.0, 0.4, 1.0))
    engine = RecordingPositionEngine()

    with pytest.raises(FullGameAnalysisFailed) as raised:
        FullGameAnalyzer(engine, clock=lambda: next(clock_values)).analyse(
            _game(), _budget(max_position_time_ms=900, max_game_time_ms=1_000)
        )

    assert [request.time_limit_ms for request in engine.requests] == [900, 600]
    partial = raised.value.partial_result
    assert partial.checkpoint.completed_moves == 1
    assert partial.failure is not None
    assert partial.failure.code is FullGameFailureCode.GAME_BUDGET_EXHAUSTED
    assert engine.sessions_opened == 1
    assert engine.sessions_closed == 1


def test_cancellation_is_not_converted_to_a_partial_business_failure() -> None:
    engine = RecordingPositionEngine(fail_on_call=2, failure=KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        FullGameAnalyzer(engine, clock=lambda: 0.0).analyse(_game(), _budget())

    assert len(engine.requests) == 2
    assert engine.sessions_opened == 1
    assert engine.sessions_closed == 1


def test_move_records_and_nested_scores_are_immutable() -> None:
    result = FullGameAnalyzer(RecordingPositionEngine(), clock=lambda: 0.0).analyse(
        _game(("e2e4",)), _budget()
    )
    record = result.move_evaluations[0]
    move_attribute = "move_uci"
    score_attribute = "centipawns"

    with pytest.raises(FrozenInstanceError):
        setattr(record, move_attribute, "d2d4")
    with pytest.raises(ValidationError):
        setattr(record.before.score, score_attribute, 999)


def test_full_game_internal_types_are_absent_from_public_openapi() -> None:
    schema = str(create_app(Settings()).openapi()["components"]["schemas"])

    for forbidden in (
        "move_evaluations",
        "completed_moves",
        "evaluated_positions",
        "engine_reuse_policy",
        "configuration_snapshot",
        "failure_error_type",
        "source_position_id",
    ):
        assert forbidden not in schema
