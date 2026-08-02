from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import CurrentUserDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.game_lifecycle import PublicGameLifecycleResponse
from boardtrace_api.services.game_lifecycle import OwnerGameLifecycleService

router = APIRouter(prefix="/games", tags=["games"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/{game_id}/lifecycle",
    response_model=PublicGameLifecycleResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
        404: {"model": ErrorResponse, "description": "Game lifecycle was not found."},
    },
)
async def read_game_lifecycle(
    game_id: UUID,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
) -> PublicGameLifecycleResponse:
    lifecycle = await OwnerGameLifecycleService(session).read_for_owner(game_id, user.id)
    if lifecycle is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return PublicGameLifecycleResponse(
        game_id=lifecycle.game_id,
        lifecycle=lifecycle.lifecycle,
        completion_verified=lifecycle.completion_verified,
    )
