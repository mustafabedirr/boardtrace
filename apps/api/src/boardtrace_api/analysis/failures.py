from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError

from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.analysis.state import InvalidJobTransition


@dataclass(frozen=True)
class FailureDecision:
    retryable: bool
    code: str
    message: str


def classify_failure(error: Exception) -> FailureDecision:
    if isinstance(error, (ConnectionError, TimeoutError, OperationalError, DBAPIError)):
        return FailureDecision(
            True, "temporary_infrastructure_error", "Temporary infrastructure error"
        )
    if isinstance(error, (ValidationError, InvalidJobTransition, ValueError)):
        return FailureDecision(False, "invalid_job_request", "Job request could not be processed")
    if isinstance(error, LookupError):
        return FailureDecision(False, "job_dependency_missing", "Required job data is unavailable")
    return FailureDecision(True, "unexpected_worker_error", "Unexpected worker error")


def validate_task_payload(payload: dict[str, object]) -> AnalysisTaskPayload:
    return AnalysisTaskPayload.model_validate(payload)
