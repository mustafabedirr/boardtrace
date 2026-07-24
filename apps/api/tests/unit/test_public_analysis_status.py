from uuid import uuid4

import pytest

from boardtrace_api.models.enums import AnalysisJobStatus, GameStatus
from boardtrace_api.repositories.analysis_status import PublicReadinessAuthority
from boardtrace_api.schemas.analysis_status import PublicAnalysisReadiness
from boardtrace_api.services.analysis_status import map_public_readiness


def test_public_readiness_enum_has_exactly_five_product_states() -> None:
    assert tuple(PublicAnalysisReadiness) == (
        PublicAnalysisReadiness.NOT_STARTED,
        PublicAnalysisReadiness.QUEUED,
        PublicAnalysisReadiness.RUNNING,
        PublicAnalysisReadiness.READY,
        PublicAnalysisReadiness.FAILED,
    )


@pytest.mark.parametrize(
    ("job_status", "has_run", "game_status", "expected"),
    [
        (None, False, GameStatus.FINISHED, PublicAnalysisReadiness.NOT_STARTED),
        (
            AnalysisJobStatus.PENDING,
            False,
            GameStatus.FINISHED,
            PublicAnalysisReadiness.QUEUED,
        ),
        (
            AnalysisJobStatus.QUEUED,
            False,
            GameStatus.FINISHED,
            PublicAnalysisReadiness.QUEUED,
        ),
        (
            AnalysisJobStatus.CLAIMED,
            False,
            GameStatus.DEEP_ANALYSIS_RUNNING,
            PublicAnalysisReadiness.RUNNING,
        ),
        (
            AnalysisJobStatus.RUNNING,
            False,
            GameStatus.DEEP_ANALYSIS_RUNNING,
            PublicAnalysisReadiness.RUNNING,
        ),
        (
            AnalysisJobStatus.RETRY_SCHEDULED,
            False,
            GameStatus.FINISHED,
            PublicAnalysisReadiness.QUEUED,
        ),
        (
            AnalysisJobStatus.FAILED,
            False,
            GameStatus.FAILED,
            PublicAnalysisReadiness.FAILED,
        ),
        (
            AnalysisJobStatus.CANCELLED,
            False,
            GameStatus.FINISHED,
            PublicAnalysisReadiness.FAILED,
        ),
        (
            AnalysisJobStatus.SUCCEEDED,
            True,
            GameStatus.ANALYSIS_AVAILABLE,
            PublicAnalysisReadiness.READY,
        ),
        (
            AnalysisJobStatus.SUCCEEDED,
            False,
            GameStatus.ANALYSIS_AVAILABLE,
            PublicAnalysisReadiness.FAILED,
        ),
        (
            AnalysisJobStatus.SUCCEEDED,
            True,
            GameStatus.FINISHED,
            PublicAnalysisReadiness.FAILED,
        ),
    ],
)
def test_readiness_mapping_is_bounded_and_fail_closed(
    job_status: AnalysisJobStatus | None,
    has_run: bool,
    game_status: GameStatus,
    expected: PublicAnalysisReadiness,
) -> None:
    authority = PublicReadinessAuthority(
        game_id=uuid4(),
        game_status=game_status,
        job_status=job_status,
        has_current_complete_run=has_run,
    )

    assert map_public_readiness(authority) is expected
