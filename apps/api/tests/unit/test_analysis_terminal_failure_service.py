import logging
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.observability import InMemoryAnalysisMetrics
from boardtrace_api.services.analysis_jobs import AnalysisJobTerminalFailureService


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class SessionSpy:
    def __init__(self, sequence: list[str]) -> None:
        self.sequence = sequence

    async def commit(self) -> None:
        self.sequence.append("commit")

    async def rollback(self) -> None:
        self.sequence.append("rollback")


class TerminalFailureRepositorySpy:
    def __init__(self, sequence: list[str], accepted: bool) -> None:
        self.sequence = sequence
        self.accepted = accepted

    async def fail_job(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        now: datetime,
        lease_generation: int | None = None,
    ) -> bool:
        self.sequence.append("mutation")
        return self.accepted


class FailingMetrics:
    def increment(
        self, name: str, *, status: str | None = None, error_code: str | None = None
    ) -> None:
        raise RuntimeError("metrics adapter failure")

    def observe(self, name: str, value: float) -> None:
        raise AssertionError("not used")

    def set_gauge(self, name: str, value: float) -> None:
        raise AssertionError("not used")


def service(
    sequence: list[str], accepted: bool, metrics: InMemoryAnalysisMetrics | FailingMetrics
) -> AnalysisJobTerminalFailureService:
    return AnalysisJobTerminalFailureService(
        cast(AsyncSession, SessionSpy(sequence)),
        metrics,
        TerminalFailureRepositorySpy(sequence, accepted),
    )


@pytest.mark.asyncio
async def test_accepted_terminal_failure_commits_before_success_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence: list[str] = []
    metrics = InMemoryAnalysisMetrics()
    job_id = uuid4()
    audit_records: list[tuple[str, dict[str, object]]] = []

    def record_audit(event: str, **context: object) -> None:
        audit_records.append((event, context))

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", record_audit)

    async def hook() -> None:
        sequence.append("hook")

    accepted = await service(sequence, True, metrics).fail_job(
        job_id,
        "worker-a",
        "terminal_code",
        "terminal message",
        datetime.now(UTC),
        4,
        hook,
    )

    assert accepted is True
    assert sequence == ["mutation", "hook", "commit"]
    assert metrics.counters[("analysis_jobs_failed_total", "FAILED", "terminal_code")] == 1
    assert audit_records == [
        (
            "analysis_job_failed",
            {
                "job_id": str(job_id),
                "worker_id": "worker-a",
                "status": "FAILED",
                "error_code": "terminal_code",
            },
        )
    ]


@pytest.mark.asyncio
async def test_rejected_terminal_failure_suppresses_success_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence: list[str] = []
    metrics = InMemoryAnalysisMetrics()
    audit_records: list[tuple[str, dict[str, object]]] = []

    def record_audit(event: str, **context: object) -> None:
        audit_records.append((event, context))

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", record_audit)
    accepted = await service(sequence, False, metrics).fail_job(
        uuid4(), "stale-worker", "terminal_code", "terminal message", datetime.now(UTC)
    )

    assert accepted is False
    assert sequence == ["mutation", "commit"]
    assert metrics.counters[("analysis_jobs_failed_total", "FAILED", "terminal_code")] == 0
    assert (
        metrics.counters[
            ("analysis_job_invalid_transitions_total", None, "terminal_failure_rejected")
        ]
        == 1
    )
    assert audit_records[0][0] == "analysis_job_invalid_transition_rejected"
    assert len(audit_records) == 1


@pytest.mark.asyncio
async def test_before_commit_failure_rolls_back_without_terminal_success_signals(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sequence: list[str] = []
    metrics = InMemoryAnalysisMetrics()

    async def hook() -> None:
        sequence.append("hook")
        raise RuntimeError("controlled persistence failure")

    logger = logging.getLogger("boardtrace_api.analysis")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="boardtrace_api.analysis"):
            with pytest.raises(RuntimeError, match="controlled persistence failure"):
                await service(sequence, True, metrics).fail_job(
                    uuid4(),
                    "worker-a",
                    "terminal_code",
                    "terminal message",
                    datetime.now(UTC),
                    4,
                    hook,
                )
    finally:
        logger.removeHandler(caplog.handler)

    assert sequence == ["mutation", "hook", "rollback"]
    assert not metrics.counters
    assert not [record for record in caplog.records if record.getMessage() == "analysis_job_failed"]


@pytest.mark.asyncio
async def test_audit_and_metrics_adapter_failures_do_not_change_committed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence: list[str] = []

    def fail_audit(event: str, **context: object) -> None:
        raise RuntimeError("audit adapter failure")

    monkeypatch.setattr("boardtrace_api.analysis.observability.audit_event", fail_audit)
    logger = logging.getLogger("boardtrace_api.analysis")
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
        accepted = await service(sequence, True, FailingMetrics()).fail_job(
            uuid4(), "worker-a", "terminal_code", "terminal message", datetime.now(UTC)
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)

    assert accepted is True
    assert sequence == ["mutation", "commit"]
    messages = [record.getMessage() for record in handler.records]
    assert "analysis audit event failed" in messages
    assert "analysis metric increment failed" in messages
