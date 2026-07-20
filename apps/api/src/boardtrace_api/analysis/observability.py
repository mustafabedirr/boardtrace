import logging
from collections import Counter
from typing import Protocol

ANALYSIS_COUNTERS = frozenset(
    {
        "analysis_jobs_created_total",
        "analysis_jobs_enqueue_requested_total",
        "analysis_jobs_published_total",
        "analysis_jobs_publish_failed_total",
        "analysis_jobs_claimed_total",
        "analysis_jobs_started_total",
        "analysis_jobs_heartbeat_total",
        "analysis_jobs_succeeded_total",
        "analysis_jobs_failed_total",
        "analysis_jobs_retried_total",
        "analysis_job_lease_recoveries_total",
        "analysis_job_duplicate_deliveries_total",
        "analysis_job_payload_rejections_total",
        "analysis_job_invalid_transitions_total",
        "analysis_job_max_attempts_exhausted_total",
    }
)
ANALYSIS_OBSERVATIONS = frozenset(
    {
        "analysis_job_duration_seconds",
        "analysis_queue_delay_seconds",
        "analysis_outbox_publish_duration_seconds",
    }
)
ANALYSIS_GAUGES = frozenset({"analysis_jobs_inflight", "analysis_outbox_pending"})
ANALYSIS_AUDIT_EVENTS = frozenset(
    {
        "analysis_job_created",
        "analysis_job_enqueue_requested",
        "analysis_job_published",
        "analysis_job_publish_failed",
        "analysis_job_claimed",
        "analysis_job_started",
        "analysis_job_heartbeat",
        "analysis_job_succeeded",
        "analysis_job_retry_scheduled",
        "analysis_job_failed",
        "analysis_job_lease_recovered",
        "analysis_job_duplicate_delivery_ignored",
        "analysis_job_invalid_transition_rejected",
        "analysis_job_payload_rejected",
        "analysis_job_max_attempts_exhausted",
    }
)
_AUDIT_CONTEXT_LIMITS = {
    "job_id": 64,
    "correlation_id": 64,
    "status": 64,
    "attempt_count": 16,
    "delivery_generation": 16,
    "worker_id": 255,
    "error_code": 100,
    "duration_seconds": 32,
}


class AnalysisMetrics(Protocol):
    def increment(
        self, name: str, *, status: str | None = None, error_code: str | None = None
    ) -> None: ...

    def observe(self, name: str, value: float) -> None: ...

    def set_gauge(self, name: str, value: float) -> None: ...


class InMemoryAnalysisMetrics:
    """Test adapter; production wiring can supply a metrics backend without domain coupling."""

    def __init__(self) -> None:
        self.counters: Counter[tuple[str, str | None, str | None]] = Counter()
        self.observations: list[tuple[str, float]] = []
        self.gauges: dict[str, float] = {}

    def increment(
        self, name: str, *, status: str | None = None, error_code: str | None = None
    ) -> None:
        if name not in ANALYSIS_COUNTERS:
            raise ValueError("unknown analysis counter")
        if status is not None and len(status) > 64:
            raise ValueError("status label is not bounded")
        if error_code is not None and len(error_code) > 100:
            raise ValueError("error code label is not bounded")
        self.counters[(name, status, error_code)] += 1

    def observe(self, name: str, value: float) -> None:
        if name not in ANALYSIS_OBSERVATIONS:
            raise ValueError("unknown analysis observation")
        self.observations.append((name, value))

    def set_gauge(self, name: str, value: float) -> None:
        if name not in ANALYSIS_GAUGES:
            raise ValueError("unknown analysis gauge")
        self.gauges[name] = value


class NoOpAnalysisMetrics:
    """Safe production default that cannot affect queue business transactions."""

    def increment(
        self, name: str, *, status: str | None = None, error_code: str | None = None
    ) -> None:
        return None

    def observe(self, name: str, value: float) -> None:
        return None

    def set_gauge(self, name: str, value: float) -> None:
        return None


def metric_increment(
    metrics: AnalysisMetrics, name: str, *, status: str | None = None, error_code: str | None = None
) -> None:
    """Metrics are observational and must never change a committed job outcome."""
    try:
        metrics.increment(name, status=status, error_code=error_code)
    except Exception:
        logging.getLogger("boardtrace_api.analysis").warning("analysis metric increment failed")


def metric_observe(metrics: AnalysisMetrics, name: str, value: float) -> None:
    try:
        metrics.observe(name, value)
    except Exception:
        logging.getLogger("boardtrace_api.analysis").warning("analysis metric observation failed")


def metric_gauge(metrics: AnalysisMetrics, name: str, value: float) -> None:
    try:
        metrics.set_gauge(name, value)
    except Exception:
        logging.getLogger("boardtrace_api.analysis").warning("analysis metric gauge failed")


def audit_event(event: str, **context: object) -> None:
    """Emit a bounded, secret-free lifecycle event from production code only."""
    if event not in ANALYSIS_AUDIT_EVENTS:
        raise ValueError("unknown analysis audit event")
    safe_context = {
        key: str(value)[:limit]
        for key, value in context.items()
        if key in _AUDIT_CONTEXT_LIMITS and value is not None
        for limit in [_AUDIT_CONTEXT_LIMITS[key]]
    }
    logging.getLogger("boardtrace_api.analysis").info(event, extra=safe_context)


def audit_event_safely(event: str, **context: object) -> None:
    """Keep audit-adapter failures outside committed lifecycle outcomes."""

    try:
        audit_event(event, **context)
    except Exception:
        logging.getLogger("boardtrace_api.analysis").warning("analysis audit event failed")
