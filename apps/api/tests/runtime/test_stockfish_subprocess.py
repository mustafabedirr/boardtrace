"""Opt-in closure tests against a real native Stockfish executable."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import chess.engine
import pytest

from boardtrace_api.analysis.full_game import (
    CompletedGameAnalysisInput,
    FullGameAnalysisBudget,
    FullGameAnalysisStatus,
    FullGameAnalyzer,
)
from boardtrace_api.analysis.stockfish import (
    PostGameEngineAuthorization,
    StockfishAnalysisRequest,
    StockfishEngine,
    UciEngine,
)
from boardtrace_api.models.enums import GameStatus

pytestmark = [pytest.mark.runtime]


def _stockfish_path() -> str:
    configured = os.environ.get("BOARDTRACE_TEST_STOCKFISH_PATH")
    if configured is None or not Path(configured).is_file():
        pytest.skip("BOARDTRACE_TEST_STOCKFISH_PATH does not name a real Stockfish executable")
    return configured


def test_real_uci_readiness_analysis_cleanup_and_fresh_process_repeat() -> None:
    executable = _stockfish_path()
    processes: list[chess.engine.SimpleEngine] = []

    def launch(path: str, timeout_seconds: float) -> UciEngine:
        # Returning from popen_uci proves that the native process completed the UCI
        # identification/readiness startup handshake within the supplied bound.
        process = chess.engine.SimpleEngine.popen_uci(path, timeout=timeout_seconds)
        processes.append(process)
        return process

    game_id = uuid4()
    authorization = PostGameEngineAuthorization(
        game_id=game_id,
        game_status=GameStatus.FINISHED,
        completion_verified_at=datetime.now(UTC),
    )
    engine = StockfishEngine(executable, threads=1, hash_mb=16, timeout_seconds=10, launcher=launch)

    results = [
        engine.analyse(
            authorization,
            StockfishAnalysisRequest(
                game_id=game_id,
                position_id=uuid4(),
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                depth=6,
            ),
        )
        for _ in range(2)
    ]

    assert len(processes) == 2
    assert processes[0] is not processes[1]
    assert all(process.transport.get_returncode() is not None for process in processes)
    assert all(result.engine_name.lower().startswith("stockfish") for result in results)
    assert all(result.best_move_uci in result.principal_variation_uci for result in results)


def test_real_stockfish_runs_a_narrow_bounded_full_game_smoke() -> None:
    executable = _stockfish_path()
    processes: list[chess.engine.SimpleEngine] = []

    def launch(path: str, timeout_seconds: float) -> UciEngine:
        process = chess.engine.SimpleEngine.popen_uci(path, timeout=timeout_seconds)
        processes.append(process)
        return process

    game = CompletedGameAnalysisInput(
        game_id=uuid4(),
        game_status=GameStatus.FINISHED,
        completion_verified_at=datetime.now(UTC),
        initial_fen=None,
        normalized_moves_uci=("e2e4", "e7e5", "g1f3"),
    )
    result = FullGameAnalyzer(
        StockfishEngine(
            executable,
            threads=1,
            hash_mb=16,
            timeout_seconds=5,
            launcher=launch,
        )
    ).analyse(
        game,
        FullGameAnalysisBudget(
            depth=4,
            max_position_time_ms=1_000,
            max_moves=3,
            max_positions=4,
            max_game_time_ms=5_000,
        ),
    )

    assert result.status is FullGameAnalysisStatus.COMPLETE
    assert [move.move_uci for move in result.move_evaluations] == ["e2e4", "e7e5", "g1f3"]
    assert result.checkpoint.evaluated_positions == 4
    assert len(processes) == 1
    assert all(process.transport.get_returncode() is not None for process in processes)
