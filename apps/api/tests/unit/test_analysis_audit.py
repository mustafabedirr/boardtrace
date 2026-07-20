import logging

import pytest

from boardtrace_api.analysis.observability import audit_event


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_audit_event_has_stable_name_and_strips_secret_like_context() -> None:
    logger = logging.getLogger("boardtrace_api.analysis")
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
        audit_event(
            "analysis_job_publish_failed",
            job_id="job-1",
            error_code="queue_temporarily_unavailable",
            redis_url="not-permitted",
            exception="not-permitted",
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        logging.disable(previous_disable)
    record = handler.records[-1]
    assert record.getMessage() == "analysis_job_publish_failed"
    assert record.__dict__["job_id"] == "job-1"
    assert record.__dict__["error_code"] == "queue_temporarily_unavailable"
    assert not hasattr(record, "redis_url")
    assert not hasattr(record, "exception")


def test_audit_event_rejects_unknown_lifecycle_name() -> None:
    with pytest.raises(ValueError, match="unknown analysis audit event"):
        audit_event("analysis_job_unreviewed_event")
