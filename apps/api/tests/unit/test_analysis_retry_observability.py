from datetime import timedelta

import pytest

from boardtrace_api.analysis.observability import (
    InMemoryAnalysisMetrics,
    metric_gauge,
    metric_increment,
    metric_observe,
)
from boardtrace_api.analysis.retry import RetryPolicy, ZeroJitter


class FixedJitter:
    def __init__(self, value: int) -> None:
        self._value = value

    def seconds(self, upper_bound: int) -> int:
        return self._value


def test_retry_policy_is_deterministic_and_clamped() -> None:
    policy = RetryPolicy(10, 40, 5)
    assert policy.delay_for_attempt(1, ZeroJitter()) == timedelta(seconds=10)
    assert policy.delay_for_attempt(2, ZeroJitter()) == timedelta(seconds=20)
    assert policy.delay_for_attempt(9, FixedJitter(5)) == timedelta(seconds=45)
    assert policy.delay_for_attempt(9, FixedJitter(99)) == timedelta(seconds=45)


@pytest.mark.parametrize("attempt", [0, -1])
def test_retry_policy_rejects_invalid_attempt(attempt: int) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(10, 40, 0).delay_for_attempt(attempt, ZeroJitter())


def test_retry_policy_rejects_invalid_configuration_and_jitter() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(0, 10, 0)
    with pytest.raises(ValueError):
        RetryPolicy(10, 5, 0)
    with pytest.raises(ValueError):
        RetryPolicy(10, 10, -1)
    with pytest.raises(ValueError):
        RetryPolicy(10, 10, 1).delay_for_attempt(1, FixedJitter(-1))


def test_metrics_adapter_uses_only_bounded_dimensions() -> None:
    metrics = InMemoryAnalysisMetrics()
    metrics.increment("analysis_jobs_created_total", status="PENDING")
    metrics.observe("analysis_job_duration_seconds", 0.25)
    assert metrics.counters[("analysis_jobs_created_total", "PENDING", None)] == 1
    assert metrics.observations == [("analysis_job_duration_seconds", 0.25)]


def test_metrics_adapter_tracks_only_known_state_derived_gauges() -> None:
    metrics = InMemoryAnalysisMetrics()
    metrics.set_gauge("analysis_jobs_inflight", 2)
    metrics.set_gauge("analysis_outbox_pending", 4)
    assert metrics.gauges == {"analysis_jobs_inflight": 2, "analysis_outbox_pending": 4}
    with pytest.raises(ValueError):
        metrics.set_gauge("job_id", 1)


class FailingMetrics:
    def increment(
        self, name: str, *, status: str | None = None, error_code: str | None = None
    ) -> None:
        raise RuntimeError("adapter unavailable")

    def observe(self, name: str, value: float) -> None:
        raise RuntimeError("adapter unavailable")

    def set_gauge(self, name: str, value: float) -> None:
        raise RuntimeError("adapter unavailable")


def test_metrics_failures_are_isolated_from_business_flow() -> None:
    metrics = FailingMetrics()
    metric_increment(metrics, "analysis_jobs_created_total")
    metric_observe(metrics, "analysis_job_duration_seconds", 0.1)
    metric_gauge(metrics, "analysis_jobs_inflight", 1)
