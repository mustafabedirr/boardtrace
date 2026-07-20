from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import AnalysisStatusReaderDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.schemas.analysis import AnalysisJobStatusResponse
from boardtrace_api.schemas.errors import ErrorResponse

router = APIRouter(prefix="/analysis/jobs", tags=["analysis-jobs"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/{job_id}",
    response_model=AnalysisJobStatusResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
        404: {"model": ErrorResponse, "description": "Analysis job was not found."},
    },
)
async def analysis_job_status(
    job_id: UUID, response: Response, user: AnalysisStatusReaderDep, session: SessionDep
) -> AnalysisJobStatusResponse:
    job = await AnalysisJobRepository(session).get_safe_status(job_id, user.id)
    if job is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return AnalysisJobStatusResponse(
        job_id=job.id,
        game_id=job.game_id,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        failed_at=job.failed_at,
        next_attempt_at=job.next_attempt_at,
    )
