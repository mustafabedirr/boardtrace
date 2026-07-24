"""Fail-closed public readiness mapping with bounded polling guidance."""

from typing import Final, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models.enums import AnalysisJobStatus, GameStatus
from boardtrace_api.repositories.analysis_status import (
    AnalysisStatusRepository,
    PublicReadinessAuthority,
)
from boardtrace_api.schemas.analysis_status import (
    PublicAnalysisReadiness,
    PublicAnalysisStatusResponse,
    PublicPollingGuidance,
)

MINIMUM_POLL_INTERVAL_MS: Final[Literal[2000]] = 2_000
MAXIMUM_POLL_INTERVAL_MS: Final[Literal[15000]] = 15_000
POLL_BACKOFF_MULTIPLIER = 1.5


class PublicAnalysisStatusNotFoundError(RuntimeError):
    pass


class PublicAnalysisStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = AnalysisStatusRepository(session)

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> PublicAnalysisStatusResponse:
        authority = await self._repository.get_owner_readiness_authority(
            game_id,
            requesting_user_id,
        )
        if authority is None:
            raise PublicAnalysisStatusNotFoundError("post-game analysis status was not found")
        readiness = map_public_readiness(authority)
        return PublicAnalysisStatusResponse(
            game_id=authority.game_id,
            readiness=readiness,
            result_available=readiness is PublicAnalysisReadiness.READY,
            polling=_polling_guidance(readiness, authority.job_status),
        )


def map_public_readiness(
    authority: PublicReadinessAuthority,
) -> PublicAnalysisReadiness:
    status = authority.job_status
    if status is None:
        return PublicAnalysisReadiness.NOT_STARTED
    if status in {AnalysisJobStatus.PENDING, AnalysisJobStatus.QUEUED}:
        return PublicAnalysisReadiness.QUEUED
    if status in {AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING}:
        return PublicAnalysisReadiness.RUNNING
    if status is AnalysisJobStatus.RETRY_SCHEDULED:
        return PublicAnalysisReadiness.QUEUED
    if status in {AnalysisJobStatus.FAILED, AnalysisJobStatus.CANCELLED}:
        return PublicAnalysisReadiness.FAILED
    if (
        status is AnalysisJobStatus.SUCCEEDED
        and authority.has_current_complete_run
        and authority.game_status is GameStatus.ANALYSIS_AVAILABLE
    ):
        return PublicAnalysisReadiness.READY
    return PublicAnalysisReadiness.FAILED


def _polling_guidance(
    readiness: PublicAnalysisReadiness,
    internal_job_status: AnalysisJobStatus | None,
) -> PublicPollingGuidance:
    retry_after: Literal[2000, 3000, 5000] | None
    if internal_job_status is AnalysisJobStatus.RETRY_SCHEDULED:
        retry_after = 5_000
    elif readiness is PublicAnalysisReadiness.QUEUED:
        retry_after = 2_000
    elif readiness is PublicAnalysisReadiness.RUNNING:
        retry_after = 3_000
    else:
        retry_after = None
    return PublicPollingGuidance(
        should_retry=retry_after is not None,
        retry_after_ms=retry_after,
        minimum_interval_ms=MINIMUM_POLL_INTERVAL_MS,
        maximum_interval_ms=MAXIMUM_POLL_INTERVAL_MS,
        backoff_multiplier=POLL_BACKOFF_MULTIPLIER,
    )
