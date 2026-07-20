import pytest
from pydantic import ValidationError

from boardtrace_api.analysis.failures import classify_failure, validate_task_payload
from boardtrace_api.analysis.state import InvalidJobTransition


@pytest.mark.parametrize(
    "error",
    [ConnectionError("secret"), TimeoutError("secret"), RuntimeError("unknown")],
)
def test_retryable_and_unknown_failures_are_sanitized(error: Exception) -> None:
    decision = classify_failure(error)
    assert decision.retryable
    assert "secret" not in decision.message
    assert len(decision.message) <= 100


@pytest.mark.parametrize(
    "error", [ValueError("bad"), InvalidJobTransition("bad"), LookupError("bad")]
)
def test_permanent_failures_are_not_retried(error: Exception) -> None:
    assert not classify_failure(error).retryable


def test_invalid_payload_is_classified_without_raw_payload_leakage() -> None:
    with pytest.raises(ValidationError) as error:
        validate_task_payload({"schema_version": 2})
    decision = classify_failure(error.value)
    assert not decision.retryable
    assert "schema_version" not in decision.message
