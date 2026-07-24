"""Typed, worker-only Stockfish UCI adapter.

This module deliberately has no FastAPI dependency and never launches an engine at
import time.  Callers must pass post-game authorization explicitly before a native
Stockfish process can receive a position.
"""

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Protocol
from uuid import UUID

import chess
import chess.engine
from pydantic import BaseModel, ConfigDict, Field, model_validator

from boardtrace_api.config import Settings
from boardtrace_api.models.enums import GameStatus

logger = logging.getLogger("boardtrace_api.analysis.stockfish")


class EngineExecutionForbidden(PermissionError):
    """Raised before a position can reach an engine for a non-finalized game."""


class StockfishUnavailable(RuntimeError):
    """Raised when the configured native Stockfish process cannot be started."""


class StockfishExecutionError(RuntimeError):
    """Raised when a started engine cannot provide a complete analysis response."""


class StockfishAnalysisTimeout(StockfishExecutionError):
    """Raised when Stockfish exceeds the bounded UCI command timeout."""


class InvalidEnginePosition(ValueError):
    """Raised when an internal caller supplies an invalid FEN position."""


@dataclass(frozen=True)
class PostGameEngineAuthorization:
    """Server-derived release facts required before engine execution."""

    game_id: UUID
    game_status: GameStatus
    completion_verified_at: datetime | None

    def require_execution_allowed(self) -> None:
        if (
            self.game_status not in {GameStatus.FINISHED, GameStatus.DEEP_ANALYSIS_RUNNING}
            or self.completion_verified_at is None
        ):
            raise EngineExecutionForbidden("engine execution is locked until game completion")


class StockfishAnalysisRequest(BaseModel):
    """Internal-only request; it is never a client-facing API schema."""

    game_id: UUID
    position_id: UUID
    fen: str = Field(min_length=1, max_length=128)
    depth: int = Field(ge=1, le=99)
    time_limit_ms: int | None = Field(default=None, ge=1, le=300_000)


class StockfishScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    centipawns: int | None = None
    mate_in: int | None = None

    @model_validator(mode="after")
    def require_exactly_one_score(self) -> "StockfishScore":
        if (self.centipawns is None) == (self.mate_in is None):
            raise ValueError("exactly one Stockfish score representation is required")
        return self


class StockfishAnalysisResult(BaseModel):
    """Internal engine output, intentionally separate from public response schemas."""

    game_id: UUID
    position_id: UUID
    score: StockfishScore
    best_move_uci: str
    principal_variation_uci: tuple[str, ...]
    depth: int | None = Field(default=None, ge=1)
    nodes: int | None = Field(default=None, ge=0)
    time_ms: int | None = Field(default=None, ge=0)
    engine_name: str
    engine_version: str | None = None


class UciEngine(Protocol):
    @property
    def id(self) -> Mapping[str, str]: ...

    def configure(self, options: Mapping[str, chess.engine.ConfigValue]) -> None: ...

    def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.InfoDict: ...

    def quit(self) -> None: ...


EngineLauncher = Callable[[str, float], UciEngine]


def _launch_stockfish(executable_path: str, timeout_seconds: float) -> UciEngine:
    # popen_uci completes the UCI initialization handshake before returning.  The
    # timeout also bounds subsequent protocol commands, including analyse().
    return chess.engine.SimpleEngine.popen_uci(executable_path, timeout=timeout_seconds)


class StockfishEngine:
    """Owns bounded UCI sessions; standalone calls remain short-lived."""

    def __init__(
        self,
        executable_path: str | None,
        threads: int,
        hash_mb: int,
        timeout_seconds: float = 30.0,
        launcher: EngineLauncher = _launch_stockfish,
    ) -> None:
        self._executable_path = executable_path
        self._threads = threads
        self._hash_mb = hash_mb
        self._timeout_seconds = timeout_seconds
        self._launcher = launcher
        self._execution_lock = Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "StockfishEngine":
        return cls(
            settings.stockfish_path,
            settings.stockfish_threads,
            settings.stockfish_hash_mb,
            settings.stockfish_timeout_seconds,
        )

    def analyse(
        self,
        authorization: PostGameEngineAuthorization,
        request: StockfishAnalysisRequest,
    ) -> StockfishAnalysisResult:
        authorization.require_execution_allowed()
        if authorization.game_id != request.game_id:
            raise EngineExecutionForbidden("engine authorization does not match the requested game")
        self._parse_board(request.fen)
        with self.analysis_session(authorization) as session:
            return session.analyse(request)

    def analysis_session(
        self, authorization: PostGameEngineAuthorization
    ) -> AbstractContextManager["StockfishAnalysisSession"]:
        """Create one serialized process owner for one bounded analysis operation."""
        return StockfishAnalysisSession(self, authorization)

    @staticmethod
    def _parse_board(fen: str) -> chess.Board:
        try:
            return chess.Board(fen)
        except ValueError as error:
            raise InvalidEnginePosition("invalid engine position") from error

    def _start_engine(self) -> UciEngine:
        if not self._executable_path:
            raise StockfishUnavailable("Stockfish executable is not configured")
        try:
            return self._launcher(self._executable_path, self._timeout_seconds)
        except TimeoutError as error:
            raise StockfishUnavailable("Stockfish UCI startup timed out") from error
        except (FileNotFoundError, OSError, chess.engine.EngineError) as error:
            raise StockfishUnavailable("Stockfish executable is unavailable") from error

    @staticmethod
    def _stop_engine(engine: UciEngine) -> None:
        """Best-effort invalidation without masking analysis errors or cancellation."""
        try:
            engine.quit()
        except (TimeoutError, OSError, chess.engine.EngineError) as error:
            # A timed-out or crashed process is already unusable.  SimpleEngine's
            # transport teardown invalidates it; the next request always starts fresh.
            logger.warning(
                "stockfish_process_cleanup_failed",
                extra={"error_type": type(error).__name__},
            )

    @staticmethod
    def _build_result(
        request: StockfishAnalysisRequest,
        board: chess.Board,
        info: chess.engine.InfoDict,
        engine: UciEngine,
    ) -> StockfishAnalysisResult:
        score = info.get("score")
        variation = info.get("pv")
        if not isinstance(score, chess.engine.PovScore) or not variation:
            raise StockfishExecutionError("Stockfish returned incomplete analysis")
        relative_score = score.pov(board.turn)
        mate_in = relative_score.mate()
        normalized_score = (
            StockfishScore(mate_in=mate_in)
            if mate_in is not None
            else StockfishScore(centipawns=relative_score.score())
        )
        if normalized_score.centipawns is None and normalized_score.mate_in is None:
            raise StockfishExecutionError("Stockfish returned an unsupported score")
        engine_id = engine.id
        engine_name = str(engine_id.get("name", "Stockfish"))
        engine_version = engine_id.get("version")
        return StockfishAnalysisResult(
            game_id=request.game_id,
            position_id=request.position_id,
            score=normalized_score,
            best_move_uci=variation[0].uci(),
            principal_variation_uci=tuple(move.uci() for move in variation),
            depth=_optional_nonnegative_int(info.get("depth"), minimum=1),
            nodes=_optional_nonnegative_int(info.get("nodes")),
            time_ms=_time_ms(info.get("time")),
            engine_name=engine_name,
            engine_version=str(engine_version) if engine_version is not None else None,
        )


def _optional_nonnegative_int(value: object, minimum: int = 0) -> int | None:
    if isinstance(value, int) and value >= minimum:
        return value
    return None


def _time_ms(value: object) -> int | None:
    if isinstance(value, (int, float)) and value >= 0:
        return round(value * 1000)
    return None


class StockfishAnalysisSession:
    """One configured Stockfish subprocess shared by sequential position calls."""

    def __init__(
        self,
        owner: StockfishEngine,
        authorization: PostGameEngineAuthorization,
    ) -> None:
        self._owner = owner
        self._authorization = authorization
        self._engine: UciEngine | None = None

    def __enter__(self) -> "StockfishAnalysisSession":
        self._authorization.require_execution_allowed()
        self._owner._execution_lock.acquire()
        engine: UciEngine | None = None
        try:
            engine = self._owner._start_engine()
            engine.configure({"Threads": self._owner._threads, "Hash": self._owner._hash_mb})
            self._engine = engine
            return self
        except BaseException as error:
            if engine is not None:
                self._owner._stop_engine(engine)
            self._owner._execution_lock.release()
            if isinstance(error, TimeoutError):
                raise StockfishAnalysisTimeout("Stockfish configuration timed out") from error
            if isinstance(error, chess.engine.EngineError):
                raise StockfishExecutionError("Stockfish configuration failed") from error
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        engine = self._engine
        self._engine = None
        try:
            if engine is not None:
                self._owner._stop_engine(engine)
        finally:
            self._owner._execution_lock.release()

    def analyse(self, request: StockfishAnalysisRequest) -> StockfishAnalysisResult:
        engine = self._engine
        if engine is None:
            raise StockfishExecutionError("Stockfish analysis session is not active")
        if self._authorization.game_id != request.game_id:
            raise EngineExecutionForbidden("engine authorization does not match the requested game")
        board = self._owner._parse_board(request.fen)
        try:
            info = engine.analyse(
                board,
                chess.engine.Limit(
                    depth=request.depth,
                    time=request.time_limit_ms / 1000
                    if request.time_limit_ms is not None
                    else None,
                ),
            )
            return self._owner._build_result(request, board, info, engine)
        except TimeoutError as error:
            self._invalidate(engine)
            raise StockfishAnalysisTimeout("Stockfish analysis timed out") from error
        except chess.engine.EngineError as error:
            self._invalidate(engine)
            raise StockfishExecutionError("Stockfish analysis failed") from error
        except StockfishExecutionError:
            self._invalidate(engine)
            raise

    def _invalidate(self, engine: UciEngine) -> None:
        self._engine = None
        self._owner._stop_engine(engine)
