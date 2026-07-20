"""Terminal outcome observability contracts for completed-game ingestion."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol
from uuid import UUID

_LOGGER = logging.getLogger("boardtrace_api.ingestion")
_INGESTION_OPERATION = "completed_game_ingestion"


class IngestionTerminalOutcome(StrEnum):
    """Stable terminal outcomes exposed by the ingestion observer contract."""

    SUCCESS = "success"
    FAILURE = "failure"


class IngestionTerminalObserver(Protocol):
    """Records a completed ingestion outcome without participating in persistence."""

    async def record_terminal_outcome(
        self,
        *,
        outcome: IngestionTerminalOutcome,
        operation: str,
        game_id: UUID | None,
        error_type: str | None,
    ) -> None: ...


class LoggingIngestionTerminalObserver:
    """Stateless production observer using the application's standard logger."""

    async def record_terminal_outcome(
        self,
        *,
        outcome: IngestionTerminalOutcome,
        operation: str,
        game_id: UUID | None,
        error_type: str | None,
    ) -> None:
        _LOGGER.info(
            "ingestion_terminal_outcome",
            extra={
                "operation": operation,
                "outcome": outcome.value,
                "game_id": str(game_id) if game_id is not None else None,
                "error_type": error_type,
            },
        )


async def record_terminal_outcome_safely(
    *,
    observer: IngestionTerminalObserver,
    outcome: IngestionTerminalOutcome,
    operation: str,
    game_id: UUID | None,
    error_type: str | None,
) -> None:
    """Keep ordinary observer failures outside the ingestion business result."""

    try:
        await observer.record_terminal_outcome(
            outcome=outcome,
            operation=operation,
            game_id=game_id,
            error_type=error_type,
        )
    except Exception as error:
        _LOGGER.warning(
            "ingestion_terminal_observer_recording_failed",
            extra={
                "operation": operation,
                "outcome": outcome.value,
                "observer_error_type": type(error).__name__,
            },
        )


async def execute_ingestion_attempt[Result](
    *,
    execute: Callable[[], Awaitable[Result]],
    observer: IngestionTerminalObserver,
    game_id_from_result: Callable[[Result], UUID],
) -> Result:
    """Emit one terminal observation after the transaction executor finishes."""

    try:
        result = await execute()
    except BaseException as error:
        await record_terminal_outcome_safely(
            observer=observer,
            outcome=IngestionTerminalOutcome.FAILURE,
            operation=_INGESTION_OPERATION,
            game_id=None,
            error_type=type(error).__name__,
        )
        raise
    else:
        await record_terminal_outcome_safely(
            observer=observer,
            outcome=IngestionTerminalOutcome.SUCCESS,
            operation=_INGESTION_OPERATION,
            game_id=game_id_from_result(result),
            error_type=None,
        )
        return result


def get_ingestion_terminal_observer() -> IngestionTerminalObserver:
    """Provide the stateless observer for normal FastAPI dependency composition."""

    return LoggingIngestionTerminalObserver()
