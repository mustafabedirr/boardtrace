from boardtrace_api.models.enums import AnalysisJobStatus

TERMINAL_STATUSES = frozenset(
    {AnalysisJobStatus.SUCCEEDED, AnalysisJobStatus.FAILED, AnalysisJobStatus.CANCELLED}
)
ALLOWED_TRANSITIONS: dict[AnalysisJobStatus, frozenset[AnalysisJobStatus]] = {
    AnalysisJobStatus.PENDING: frozenset({AnalysisJobStatus.QUEUED, AnalysisJobStatus.CANCELLED}),
    AnalysisJobStatus.QUEUED: frozenset(
        {AnalysisJobStatus.CLAIMED, AnalysisJobStatus.FAILED, AnalysisJobStatus.CANCELLED}
    ),
    AnalysisJobStatus.CLAIMED: frozenset(
        {AnalysisJobStatus.RUNNING, AnalysisJobStatus.FAILED, AnalysisJobStatus.RETRY_SCHEDULED}
    ),
    AnalysisJobStatus.RUNNING: frozenset(
        {AnalysisJobStatus.SUCCEEDED, AnalysisJobStatus.FAILED, AnalysisJobStatus.RETRY_SCHEDULED}
    ),
    AnalysisJobStatus.RETRY_SCHEDULED: frozenset(
        {AnalysisJobStatus.QUEUED, AnalysisJobStatus.CANCELLED}
    ),
    AnalysisJobStatus.SUCCEEDED: frozenset(),
    AnalysisJobStatus.FAILED: frozenset(),
    AnalysisJobStatus.CANCELLED: frozenset(),
}


class InvalidJobTransition(ValueError):
    pass


def validate_transition(current: AnalysisJobStatus, target: AnalysisJobStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidJobTransition(f"Invalid analysis job transition: {current} -> {target}")
