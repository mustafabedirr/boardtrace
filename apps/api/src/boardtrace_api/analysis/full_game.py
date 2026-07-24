"""Backend-only deterministic full-game position evaluation orchestration.

This module creates immutable in-memory records only.  It has no persistence, API,
queue, worker, or client integration.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid5

import chess

from boardtrace_api.analysis.stockfish import (
    PostGameEngineAuthorization,
    StockfishAnalysisRequest,
    StockfishAnalysisResult,
    StockfishScore,
)
from boardtrace_api.models.enums import GameStatus

POSITION_ID_NAMESPACE = UUID("72bd28de-2d67-44ec-8ca5-a4c93ea92cb1")


class FullGameInputError(ValueError):
    """Raised before engine execution for an ineligible or invalid completed game."""


class FullGameFailureCode(StrEnum):
    ENGINE_EXECUTION_FAILED = "ENGINE_EXECUTION_FAILED"
    GAME_BUDGET_EXHAUSTED = "GAME_BUDGET_EXHAUSTED"


class FullGameAnalysisStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class EngineReusePolicy(StrEnum):
    """Explicit process ownership for a complete full-game operation."""

    SINGLE_PROCESS_PER_GAME = "SINGLE_PROCESS_PER_GAME"


@dataclass(frozen=True)
class CompletedGameAnalysisInput:
    """Server-owned facts; never construct this directly from a client payload."""

    game_id: UUID
    game_status: GameStatus
    completion_verified_at: datetime | None
    initial_fen: str | None
    normalized_moves_uci: tuple[str, ...]


@dataclass(frozen=True)
class FullGameAnalysisBudget:
    depth: int
    max_position_time_ms: int
    max_moves: int
    max_positions: int
    max_game_time_ms: int

    def __post_init__(self) -> None:
        if not 1 <= self.depth <= 99:
            raise ValueError("depth must be between 1 and 99")
        if not 1 <= self.max_position_time_ms <= 300_000:
            raise ValueError("max_position_time_ms must be between 1 and 300000")
        if self.max_moves < 1:
            raise ValueError("max_moves must be positive")
        if self.max_positions < 2:
            raise ValueError("max_positions must be at least two")
        if self.max_game_time_ms < 1:
            raise ValueError("max_game_time_ms must be positive")


@dataclass(frozen=True)
class PositionEvaluation:
    position_id: UUID
    ply: int
    fen: str
    side_to_move: chess.Color
    score: StockfishScore
    best_move_uci: str
    principal_variation_uci: tuple[str, ...]
    depth: int | None
    nodes: int | None
    time_ms: int | None


@dataclass(frozen=True)
class MoveEvaluation:
    ply: int
    move_uci: str
    move_san: str
    before: PositionEvaluation
    after: PositionEvaluation


@dataclass(frozen=True)
class AnalysisCheckpoint:
    total_moves: int
    total_positions: int
    completed_moves: int
    evaluated_positions: int
    last_evaluated_ply: int | None


@dataclass(frozen=True)
class FullGameFailure:
    code: FullGameFailureCode
    failed_position_ply: int
    error_type: str


@dataclass(frozen=True)
class FullGameAnalysisResult:
    game_id: UUID
    status: FullGameAnalysisStatus
    position_evaluations: tuple[PositionEvaluation, ...]
    move_evaluations: tuple[MoveEvaluation, ...]
    checkpoint: AnalysisCheckpoint
    engine_name: str | None
    engine_version: str | None
    engine_reuse_policy: EngineReusePolicy
    failure: FullGameFailure | None = None


class FullGameAnalysisFailed(RuntimeError):
    """Carries only safely completed moves when an execution cannot finish."""

    def __init__(self, partial_result: FullGameAnalysisResult) -> None:
        super().__init__("full-game analysis did not complete")
        self.partial_result = partial_result


class PositionAnalysisSession(Protocol):
    def analyse(self, request: StockfishAnalysisRequest) -> StockfishAnalysisResult: ...


class FullGameEngine(Protocol):
    def analysis_session(
        self, authorization: PostGameEngineAuthorization
    ) -> AbstractContextManager[PositionAnalysisSession]: ...


Clock = Callable[[], float]


@dataclass(frozen=True)
class _ReplayPosition:
    ply: int
    fen: str
    side_to_move: chess.Color
    preceding_move_uci: str | None
    preceding_move_san: str | None


class FullGameAnalyzer:
    """Evaluates replayed positions serially with bounded deterministic ownership."""

    def __init__(self, engine: FullGameEngine, clock: Clock = monotonic) -> None:
        self._engine = engine
        self._clock = clock

    def analyse(
        self,
        game: CompletedGameAnalysisInput,
        budget: FullGameAnalysisBudget,
    ) -> FullGameAnalysisResult:
        authorization = self._authorization(game)
        positions = self._replay(game, budget)
        started_at = self._clock()
        evaluations: list[PositionEvaluation] = []
        move_evaluations: list[MoveEvaluation] = []
        engine_name: str | None = None
        engine_version: str | None = None

        with self._engine.analysis_session(authorization) as session:
            for position in positions:
                try:
                    remaining_time_ms = budget.max_game_time_ms - self._elapsed_ms(started_at)
                    if remaining_time_ms <= 0:
                        raise _GameBudgetExhausted
                    result = session.analyse(
                        StockfishAnalysisRequest(
                            game_id=game.game_id,
                            position_id=_position_id(game.game_id, position.ply),
                            fen=position.fen,
                            depth=budget.depth,
                            time_limit_ms=min(budget.max_position_time_ms, remaining_time_ms),
                        )
                    )
                except _GameBudgetExhausted as error:
                    raise self._failure(
                        game,
                        positions,
                        move_evaluations,
                        evaluations,
                        engine_name,
                        engine_version,
                        position.ply,
                        FullGameFailureCode.GAME_BUDGET_EXHAUSTED,
                        error,
                    ) from error
                except Exception as error:
                    raise self._failure(
                        game,
                        positions,
                        move_evaluations,
                        evaluations,
                        engine_name,
                        engine_version,
                        position.ply,
                        FullGameFailureCode.ENGINE_EXECUTION_FAILED,
                        error,
                    ) from error

                evaluation = _position_evaluation(position, result)
                evaluations.append(evaluation)
                engine_name = result.engine_name
                engine_version = result.engine_version
                if position.ply > 0:
                    move_uci = position.preceding_move_uci
                    move_san = position.preceding_move_san
                    if move_uci is None or move_san is None:
                        raise AssertionError("replay position is missing its preceding move")
                    move_evaluations.append(
                        MoveEvaluation(
                            ply=position.ply,
                            move_uci=move_uci,
                            move_san=move_san,
                            before=evaluations[-2],
                            after=evaluation,
                        )
                    )

        return FullGameAnalysisResult(
            game_id=game.game_id,
            status=FullGameAnalysisStatus.COMPLETE,
            position_evaluations=tuple(evaluations),
            move_evaluations=tuple(move_evaluations),
            checkpoint=_checkpoint(positions, move_evaluations, evaluations),
            engine_name=engine_name,
            engine_version=engine_version,
            engine_reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
        )

    @staticmethod
    def _authorization(game: CompletedGameAnalysisInput) -> PostGameEngineAuthorization:
        authorization = PostGameEngineAuthorization(
            game_id=game.game_id,
            game_status=game.game_status,
            completion_verified_at=game.completion_verified_at,
        )
        try:
            authorization.require_execution_allowed()
        except PermissionError as error:
            raise FullGameInputError("game is not eligible for full-game analysis") from error
        if not game.normalized_moves_uci:
            raise FullGameInputError("completed game has no normalized moves")
        return authorization

    @staticmethod
    def _replay(
        game: CompletedGameAnalysisInput, budget: FullGameAnalysisBudget
    ) -> tuple[_ReplayPosition, ...]:
        if len(game.normalized_moves_uci) > budget.max_moves:
            raise FullGameInputError("game exceeds the configured move budget")
        if len(game.normalized_moves_uci) + 1 > budget.max_positions:
            raise FullGameInputError("game exceeds the configured position budget")
        try:
            board = chess.Board(game.initial_fen) if game.initial_fen else chess.Board()
        except ValueError as error:
            raise FullGameInputError("completed game has an invalid initial position") from error
        replay: list[_ReplayPosition] = [_ReplayPosition(0, board.fen(), board.turn, None, None)]
        for ply, move_uci in enumerate(game.normalized_moves_uci, start=1):
            try:
                move = chess.Move.from_uci(move_uci)
            except ValueError as error:
                raise FullGameInputError(f"invalid normalized move at ply {ply}") from error
            if move not in board.legal_moves:
                raise FullGameInputError(f"illegal normalized move at ply {ply}")
            move_san = board.san(move)
            board.push(move)
            replay.append(_ReplayPosition(ply, board.fen(), board.turn, move_uci, move_san))
        return tuple(replay)

    def _elapsed_ms(self, started_at: float) -> int:
        return round((self._clock() - started_at) * 1000)

    @staticmethod
    def _failure(
        game: CompletedGameAnalysisInput,
        positions: tuple[_ReplayPosition, ...],
        moves: list[MoveEvaluation],
        evaluations: list[PositionEvaluation],
        engine_name: str | None,
        engine_version: str | None,
        failed_ply: int,
        code: FullGameFailureCode,
        error: Exception,
    ) -> FullGameAnalysisFailed:
        return FullGameAnalysisFailed(
            FullGameAnalysisResult(
                game_id=game.game_id,
                status=FullGameAnalysisStatus.PARTIAL,
                position_evaluations=tuple(evaluations),
                move_evaluations=tuple(moves),
                checkpoint=_checkpoint(positions, moves, evaluations),
                engine_name=engine_name,
                engine_version=engine_version,
                engine_reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
                failure=FullGameFailure(code, failed_ply, type(error).__name__),
            )
        )


class _GameBudgetExhausted(RuntimeError):
    pass


def _position_id(game_id: UUID, ply: int) -> UUID:
    return uuid5(POSITION_ID_NAMESPACE, f"{game_id}:{ply}")


def _position_evaluation(
    position: _ReplayPosition, result: StockfishAnalysisResult
) -> PositionEvaluation:
    return PositionEvaluation(
        position_id=result.position_id,
        ply=position.ply,
        fen=position.fen,
        side_to_move=position.side_to_move,
        score=result.score.model_copy(deep=True),
        best_move_uci=result.best_move_uci,
        principal_variation_uci=result.principal_variation_uci,
        depth=result.depth,
        nodes=result.nodes,
        time_ms=result.time_ms,
    )


def _checkpoint(
    positions: tuple[_ReplayPosition, ...],
    moves: list[MoveEvaluation],
    evaluations: list[PositionEvaluation],
) -> AnalysisCheckpoint:
    return AnalysisCheckpoint(
        total_moves=len(positions) - 1,
        total_positions=len(positions),
        completed_moves=len(moves),
        evaluated_positions=len(evaluations),
        last_evaluated_ply=evaluations[-1].ply if evaluations else None,
    )
