from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError

from boardtrace_api.analysis.full_game import FullGameAnalysisFailed, FullGameFailureCode
from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.analysis.state import InvalidJobTransition
from boardtrace_api.analysis.stockfish import StockfishExecutionError, StockfishUnavailable


@dataclass(frozen=True)
class FailureDecision:
    retryable: bool
    code: str
    message: str


def classify_failure(error: Exception) -> FailureDecision:
    if isinstance(error, FullGameAnalysisFailed):
        failure = error.partial_result.failure
        if failure is not None and failure.code is FullGameFailureCode.GAME_BUDGET_EXHAUSTED:
            return FailureDecision(False, "analysis_budget_exhausted", "Analysis budget exhausted")
        return FailureDecision(True, "engine_execution_failed", "Engine execution failed")
    if isinstance(error, (StockfishUnavailable, StockfishExecutionError)):
        return FailureDecision(True, "engine_execution_failed", "Engine execution failed")
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
