import logging
from uuid import uuid4

import pytest

from boardtrace_api.ingestion_observability import (
    IngestionTerminalObserver,
    IngestionTerminalOutcome,
    LoggingIngestionTerminalObserver,
    get_ingestion_terminal_observer,
)


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_terminal_outcomes_have_stable_serialized_values() -> None:
    assert IngestionTerminalOutcome.SUCCESS.value == "success"
    assert IngestionTerminalOutcome.FAILURE.value == "failure"
    assert set(IngestionTerminalOutcome) == {
        IngestionTerminalOutcome.SUCCESS,
        IngestionTerminalOutcome.FAILURE,
    }


@pytest.mark.asyncio
async def test_production_provider_returns_usable_stateless_observer() -> None:
    observer: IngestionTerminalObserver = get_ingestion_terminal_observer()

    await observer.record_terminal_outcome(
        outcome=IngestionTerminalOutcome.SUCCESS,
        operation="completed_game_ingestion",
        game_id=uuid4(),
        error_type=None,
    )


@pytest.mark.asyncio
async def test_logging_observer_uses_stable_event_and_structured_fields() -> None:
    observer: IngestionTerminalObserver = LoggingIngestionTerminalObserver()
    game_id = uuid4()
    logger = logging.getLogger("boardtrace_api.ingestion")
    handler = RecordCollector()
    previous_level, previous_propagate, previous_disabled = (
        logger.level,
        logger.propagate,
        logger.disabled,
    )
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.disabled = False
    logger.addHandler(handler)
    try:
        await observer.record_terminal_outcome(
            outcome=IngestionTerminalOutcome.FAILURE,
            operation="completed_game_ingestion",
            game_id=game_id,
            error_type="IngestionConflictError",
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)

    record = handler.records[-1]
    assert record.getMessage() == "ingestion_terminal_outcome"
    assert record.operation == "completed_game_ingestion"
    assert record.outcome == "failure"
    assert record.game_id == str(game_id)
    assert record.error_type == "IngestionConflictError"


@pytest.mark.asyncio
async def test_logging_observer_records_success_without_failure_or_payload_fields() -> None:
    observer: IngestionTerminalObserver = LoggingIngestionTerminalObserver()
    game_id = uuid4()
    logger = logging.getLogger("boardtrace_api.ingestion")
    handler = RecordCollector()
    previous_level, previous_propagate, previous_disabled = (
        logger.level,
        logger.propagate,
        logger.disabled,
    )
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.disabled = False
    logger.addHandler(handler)
    try:
        await observer.record_terminal_outcome(
            outcome=IngestionTerminalOutcome.SUCCESS,
            operation="completed_game_ingestion",
            game_id=game_id,
            error_type=None,
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)

    record = handler.records[-1]
    assert record.getMessage() == "ingestion_terminal_outcome"
    assert record.operation == "completed_game_ingestion"
    assert record.outcome == "success"
    assert record.game_id == str(game_id)
    assert record.error_type is None
    assert not hasattr(record, "payload")
