import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.db.transactions import BeforeCommitHook, TransactionBoundary
from boardtrace_api.ingestion_observability import (
    IngestionTerminalObserver,
    IngestionTerminalOutcome,
    execute_ingestion_attempt,
)


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class ObserverFailureLogRecord(logging.LogRecord):
    outcome: str
    operation: str
    observer_error_type: str


class SessionSpy:
    def __init__(self, sequence: list[str], commit_error: BaseException | None = None) -> None:
        self.sequence = sequence
        self.commit_error = commit_error

    async def commit(self) -> None:
        self.sequence.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.sequence.append("rollback")


class RecordingObserver:
    def __init__(self, sequence: list[str]) -> None:
        self.sequence = sequence
        self.events: list[tuple[IngestionTerminalOutcome, str, UUID | None, str | None]] = []

    async def record_terminal_outcome(
        self,
        *,
        outcome: IngestionTerminalOutcome,
        operation: str,
        game_id: UUID | None,
        error_type: str | None,
    ) -> None:
        self.sequence.append(f"terminal_{outcome.value}")
        self.events.append((outcome, operation, game_id, error_type))


class FailingObserver:
    def __init__(self, sequence: list[str]) -> None:
        self.sequence = sequence
        self.calls = 0

    async def record_terminal_outcome(
        self,
        *,
        outcome: IngestionTerminalOutcome,
        operation: str,
        game_id: UUID | None,
        error_type: str | None,
    ) -> None:
        self.calls += 1
        self.sequence.append(f"terminal_{outcome.value}")
        raise RuntimeError("observer failure")


def operation(
    sequence: list[str], result: UUID, error: BaseException | None = None
) -> Callable[[], Awaitable[UUID]]:
    async def run() -> UUID:
        sequence.append("operation")
        if error is not None:
            raise error
        return result

    return run


async def execute_attempt(
    session: SessionSpy,
    observer: IngestionTerminalObserver,
    operation_callable: Callable[[], Awaitable[UUID]],
    hook: Callable[[], Awaitable[None]] | None = None,
) -> UUID:
    typed_session = cast(AsyncSession, session)
    boundary = (
        TransactionBoundary(typed_session, cast(BeforeCommitHook, hook))
        if hook is not None
        else TransactionBoundary(typed_session)
    )
    return await execute_ingestion_attempt(
        execute=lambda: boundary.execute(operation_callable),
        observer=observer,
        game_id_from_result=lambda game_id: game_id,
    )


@pytest.mark.asyncio
async def test_success_is_emitted_once_after_commit() -> None:
    sequence: list[str] = []
    game_id = uuid4()

    async def hook() -> None:
        sequence.append("hook")

    observer = RecordingObserver(sequence)
    result = await execute_attempt(
        SessionSpy(sequence), observer, operation(sequence, game_id), hook
    )

    assert result == game_id
    assert sequence == ["operation", "hook", "commit", "terminal_success"]
    assert observer.events == [
        (IngestionTerminalOutcome.SUCCESS, "completed_game_ingestion", game_id, None)
    ]


@pytest.mark.asyncio
async def test_operation_failure_is_emitted_once_after_rollback() -> None:
    sequence: list[str] = []
    error = ValueError("operation failure")
    observer = RecordingObserver(sequence)

    with pytest.raises(ValueError) as raised:
        await execute_attempt(SessionSpy(sequence), observer, operation(sequence, uuid4(), error))

    assert raised.value is error
    assert sequence == ["operation", "rollback", "terminal_failure"]
    assert observer.events == [
        (IngestionTerminalOutcome.FAILURE, "completed_game_ingestion", None, "ValueError")
    ]


@pytest.mark.asyncio
async def test_hook_failure_is_emitted_once_after_rollback() -> None:
    sequence: list[str] = []
    error = RuntimeError("hook failure")

    async def hook() -> None:
        sequence.append("hook")
        raise error

    observer = RecordingObserver(sequence)
    with pytest.raises(RuntimeError) as raised:
        await execute_attempt(SessionSpy(sequence), observer, operation(sequence, uuid4()), hook)

    assert raised.value is error
    assert sequence == ["operation", "hook", "rollback", "terminal_failure"]
    assert observer.events[0][3] == "RuntimeError"


@pytest.mark.asyncio
async def test_commit_failure_is_emitted_once_after_rollback() -> None:
    sequence: list[str] = []
    error = RuntimeError("commit failure")
    observer = RecordingObserver(sequence)

    with pytest.raises(RuntimeError) as raised:
        await execute_attempt(SessionSpy(sequence, error), observer, operation(sequence, uuid4()))

    assert raised.value is error
    assert sequence == ["operation", "commit", "rollback", "terminal_failure"]
    assert observer.events[0][3] == "RuntimeError"


@pytest.mark.asyncio
async def test_observer_failure_after_commit_preserves_result_and_logs_diagnostic() -> None:
    sequence: list[str] = []
    game_id = uuid4()
    observer = FailingObserver(sequence)
    logger = logging.getLogger("boardtrace_api.ingestion")
    handler = RecordCollector()
    previous_level, previous_propagate, previous_disabled = (
        logger.level,
        logger.propagate,
        logger.disabled,
    )
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.disabled = False
    logger.addHandler(handler)
    try:
        result = await execute_attempt(SessionSpy(sequence), observer, operation(sequence, game_id))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)

    assert result == game_id
    assert sequence == ["operation", "commit", "terminal_success"]
    assert observer.calls == 1
    record = cast(ObserverFailureLogRecord, handler.records[-1])
    assert record.getMessage() == "ingestion_terminal_observer_recording_failed"
    assert record.outcome == "success"
    assert record.operation == "completed_game_ingestion"
    assert record.observer_error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_observer_failure_during_business_failure_preserves_original_error() -> None:
    sequence: list[str] = []
    error = ValueError("business failure")
    observer = FailingObserver(sequence)
    logger = logging.getLogger("boardtrace_api.ingestion")
    handler = RecordCollector()
    previous_level, previous_propagate, previous_disabled = (
        logger.level,
        logger.propagate,
        logger.disabled,
    )
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.disabled = False
    logger.addHandler(handler)
    try:
        with pytest.raises(ValueError) as raised:
            await execute_attempt(
                SessionSpy(sequence), observer, operation(sequence, uuid4(), error)
            )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)

    assert raised.value is error
    assert sequence == ["operation", "rollback", "terminal_failure"]
    assert observer.calls == 1
    record = cast(ObserverFailureLogRecord, handler.records[-1])
    assert record.observer_error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_cancellation_is_re_raised_after_rollback_and_observer_attempt() -> None:
    sequence: list[str] = []
    observer = FailingObserver(sequence)

    with pytest.raises(asyncio.CancelledError):
        await execute_attempt(
            SessionSpy(sequence),
            observer,
            operation(sequence, uuid4(), asyncio.CancelledError()),
        )

    assert sequence == ["operation", "rollback", "terminal_failure"]
    assert observer.calls == 1
