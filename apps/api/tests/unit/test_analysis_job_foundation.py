from uuid import uuid4

import pytest
from pydantic import ValidationError

from boardtrace_api.analysis.queue import AnalysisTaskPayload
from boardtrace_api.analysis.state import InvalidJobTransition, validate_transition
from boardtrace_api.models.enums import AnalysisJobStatus


def test_state_machine_accepts_expected_worker_lifecycle() -> None:
    validate_transition(AnalysisJobStatus.PENDING, AnalysisJobStatus.QUEUED)
    validate_transition(AnalysisJobStatus.QUEUED, AnalysisJobStatus.CLAIMED)
    validate_transition(AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING)
    validate_transition(AnalysisJobStatus.RUNNING, AnalysisJobStatus.SUCCEEDED)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (AnalysisJobStatus.SUCCEEDED, AnalysisJobStatus.RUNNING),
        (AnalysisJobStatus.FAILED, AnalysisJobStatus.RUNNING),
        (AnalysisJobStatus.CANCELLED, AnalysisJobStatus.QUEUED),
        (AnalysisJobStatus.RUNNING, AnalysisJobStatus.PENDING),
    ],
)
def test_state_machine_rejects_unsafe_transitions(
    current: AnalysisJobStatus, target: AnalysisJobStatus
) -> None:
    with pytest.raises(InvalidJobTransition):
        validate_transition(current, target)


def test_task_payload_is_minimal_versioned_and_strict() -> None:
    payload = AnalysisTaskPayload(schema_version=1, job_id=uuid4(), correlation_id=uuid4())
    assert set(payload.model_dump()) == {"schema_version", "job_id", "correlation_id"}


@pytest.mark.parametrize(
    "extra",
    [
        {"evaluation": 12},
        {"best_move": "e2e4"},
        {"token": "secret"},
        {"moves": ["e2e4"]},
    ],
)
def test_task_payload_rejects_analysis_secrets_and_notation(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AnalysisTaskPayload.model_validate(
            {"schema_version": 1, "job_id": str(uuid4()), "correlation_id": str(uuid4()), **extra}
        )


def test_task_payload_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        AnalysisTaskPayload(schema_version=2, job_id=uuid4(), correlation_id=uuid4())


def test_worker_module_imports_without_starting_external_resources() -> None:
    from boardtrace_api.worker import celery_app

    assert celery_app.conf.task_default_queue == "boardtrace.analysis.jobs"
