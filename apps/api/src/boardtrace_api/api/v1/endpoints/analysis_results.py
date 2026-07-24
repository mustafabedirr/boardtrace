from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import CurrentUserDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.schemas.analysis_results import PublicGameAnalysisResponse
from boardtrace_api.schemas.analysis_status import PublicAnalysisStatusResponse
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.services.analysis_delivery import (
    PublicAnalysisNotFoundError,
    PublicAnalysisReadService,
    PublicAnalysisUnavailableError,
    compose_public_analysis_read_service,
)
from boardtrace_api.services.analysis_status import (
    PublicAnalysisStatusNotFoundError,
    PublicAnalysisStatusService,
)

router = APIRouter(prefix="/analysis/games", tags=["post-game-analysis"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_public_analysis_read_service(session: SessionDep) -> PublicAnalysisReadService:
    return compose_public_analysis_read_service(session)


PublicAnalysisReadDep = Annotated[
    PublicAnalysisReadService,
    Depends(get_public_analysis_read_service),
]


def get_public_analysis_status_service(session: SessionDep) -> PublicAnalysisStatusService:
    return PublicAnalysisStatusService(session)


PublicAnalysisStatusDep = Annotated[
    PublicAnalysisStatusService,
    Depends(get_public_analysis_status_service),
]


@router.get(
    "/{game_id}/status",
    response_model=PublicAnalysisStatusResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
        404: {
            "model": ErrorResponse,
            "description": "Post-game analysis status was not found.",
        },
    },
)
async def read_post_game_analysis_status(
    game_id: UUID,
    response: Response,
    user: CurrentUserDep,
    service: PublicAnalysisStatusDep,
) -> PublicAnalysisStatusResponse:
    try:
        result = await service.read_for_owner(game_id, user.id)
    except PublicAnalysisStatusNotFoundError as error:
        raise ApiError("not_found", "The requested resource was not found.", 404) from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if result.polling.retry_after_ms is not None:
        response.headers["Retry-After"] = str(result.polling.retry_after_ms // 1_000)
    return result


@router.get(
    "/{game_id}",
    response_model=PublicGameAnalysisResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
        404: {
            "model": ErrorResponse,
            "description": "Released post-game analysis was not found.",
        },
        503: {
            "model": ErrorResponse,
            "description": "Released analysis failed internal validation.",
        },
    },
)
async def read_post_game_analysis(
    game_id: UUID,
    response: Response,
    user: CurrentUserDep,
    service: PublicAnalysisReadDep,
) -> PublicGameAnalysisResponse:
    try:
        result = await service.read_for_owner(game_id, user.id)
    except PublicAnalysisNotFoundError as error:
        raise ApiError("not_found", "The requested resource was not found.", 404) from error
    except PublicAnalysisUnavailableError as error:
        raise ApiError(
            "analysis_unavailable",
            "The analysis result is temporarily unavailable.",
            503,
        ) from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return result
