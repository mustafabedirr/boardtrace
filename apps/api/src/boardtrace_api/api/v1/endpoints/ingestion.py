from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import ExtensionIngestUserDep, ExtensionStatusUserDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.models.enums import GameStatus
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.ingestion import CompletedGameIngestionRequest, IngestionStatusResponse
from boardtrace_api.services.ingestion import CompletedGameIngestionService, IngestionConflictError

router = APIRouter(prefix="/games", tags=["ingestion"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def response_from_game(
    game_id: UUID, status: GameStatus, moves: list[str] | None
) -> IngestionStatusResponse:
    return IngestionStatusResponse(
        id=game_id,
        ingestion_state="ACCEPTED",
        game_status=status,
        analysis_release_state="LOCKED",
        analysis_available=False,
        normalized_move_count=len(moves or []),
    )


@router.post(
    "/ingestions",
    response_model=IngestionStatusResponse,
    status_code=201,
    responses={
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
        409: {
            "model": ErrorResponse,
            "description": "Idempotency key conflicts with a different payload.",
        },
        422: {"model": ErrorResponse, "description": "Request validation failed."},
    },
)
async def ingest_completed_game(
    payload: CompletedGameIngestionRequest,
    response: Response,
    user: ExtensionIngestUserDep,
    session: SessionDep,
) -> IngestionStatusResponse:
    service = CompletedGameIngestionService(session)
    try:
        game = await service.ingest(user.id, payload)
        await session.commit()
    except IngestionConflictError as error:
        await session.rollback()
        raise ApiError("ingestion_conflict", "Ingestion could not be completed.", 409) from error
    response.headers["Cache-Control"] = "no-store"
    return response_from_game(game.id, game.status, game.normalized_moves)


@router.get(
    "/{game_id}/ingestion-status",
    response_model=IngestionStatusResponse,
    responses={401: {"model": ErrorResponse, "description": "Bearer authentication failed."}},
)
async def ingestion_status(
    game_id: UUID,
    response: Response,
    user: ExtensionStatusUserDep,
    session: SessionDep,
) -> IngestionStatusResponse:
    game = await CompletedGameIngestionService(session).get_for_user(game_id, user.id)
    if game is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return response_from_game(game.id, game.status, game.normalized_moves)
