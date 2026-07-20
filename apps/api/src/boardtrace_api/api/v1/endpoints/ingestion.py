from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import ExtensionIngestUserDep, ExtensionStatusUserDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.db.transactions import (
    BeforeCommitHook,
    TransactionBoundary,
    get_before_commit_hook,
)
from boardtrace_api.ingestion_observability import (
    IngestionTerminalObserver,
    execute_ingestion_attempt,
    get_ingestion_terminal_observer,
)
from boardtrace_api.models.enums import AnalysisJobStatus, GameStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.ingestion import CompletedGameIngestionRequest, IngestionStatusResponse
from boardtrace_api.services.ingestion import CompletedGameIngestionService, IngestionConflictError

router = APIRouter(prefix="/games", tags=["ingestion"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
BeforeCommitHookDep = Annotated[BeforeCommitHook, Depends(get_before_commit_hook)]
IngestionTerminalObserverDep = Annotated[
    IngestionTerminalObserver, Depends(get_ingestion_terminal_observer)
]


def response_from_game(
    game_id: UUID,
    status: GameStatus,
    moves: list[str] | None,
    analysis_job_id: UUID,
    analysis_job_status: AnalysisJobStatus,
) -> IngestionStatusResponse:
    return IngestionStatusResponse(
        id=game_id,
        ingestion_state="ACCEPTED",
        game_status=status,
        analysis_release_state="LOCKED",
        analysis_available=False,
        normalized_move_count=len(moves or []),
        analysis_job_id=analysis_job_id,
        analysis_job_status=analysis_job_status,
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
    before_commit: BeforeCommitHookDep,
    terminal_observer: IngestionTerminalObserverDep,
) -> IngestionStatusResponse:
    service = CompletedGameIngestionService(session)
    try:
        game = await execute_ingestion_attempt(
            execute=lambda: TransactionBoundary(session, before_commit).execute(
                lambda: service.ingest(user.id, payload)
            ),
            observer=terminal_observer,
            game_id_from_result=lambda completed_game: completed_game.id,
        )
    except IngestionConflictError as error:
        raise ApiError("ingestion_conflict", "Ingestion could not be completed.", 409) from error
    response.headers["Cache-Control"] = "no-store"
    job = await AnalysisJobRepository(session).get_by_game_profile_version(game.id, "standard", 1)
    if job is None:
        raise ApiError("analysis_job_missing", "Ingestion could not be completed.", 500)
    return response_from_game(game.id, game.status, game.normalized_moves, job.id, job.status)


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
    job = await AnalysisJobRepository(session).get_by_game_profile_version(game.id, "standard", 1)
    if job is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    return response_from_game(game.id, game.status, game.normalized_moves, job.id, job.status)
