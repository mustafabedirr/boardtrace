import time
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.observability import audit_event_safely
from boardtrace_api.api.v1.endpoints.auth import (
    CurrentUserDep,
    ExtensionIngestUserDep,
    ExtensionStatusUserDep,
)
from boardtrace_api.config import Environment
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
from boardtrace_api.models import AnalysisJob, Game
from boardtrace_api.models.enums import AnalysisJobStatus, GameStatus
from boardtrace_api.provenance import ProvenanceValidationError
from boardtrace_api.queue_admission import (
    AdmissionOutcome,
    QueueAdmission,
    QueueAdmissionController,
    QueueAdmissionUnavailable,
)
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.ingestion import (
    CompletedGameIngestionRequest,
    IngestionStatusResponse,
    QueueActionResponse,
    QueueActionState,
    QueueState,
)
from boardtrace_api.services.analysis_jobs import AnalysisJobTerminalService
from boardtrace_api.services.ingestion import CompletedGameIngestionService, IngestionConflictError

router = APIRouter(prefix="/games", tags=["ingestion"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
BeforeCommitHookDep = Annotated[BeforeCommitHook, Depends(get_before_commit_hook)]
IngestionTerminalObserverDep = Annotated[
    IngestionTerminalObserver, Depends(get_ingestion_terminal_observer)
]


def get_analysis_admission(request: Request) -> QueueAdmissionController:
    return cast(QueueAdmissionController, request.app.state.analysis_admission)


AdmissionDep = Annotated[QueueAdmissionController, Depends(get_analysis_admission)]


def response_from_game(
    game_id: UUID,
    status: GameStatus,
    moves: list[str] | None,
    analysis_job_id: UUID,
    analysis_job_status: AnalysisJobStatus,
    admission: QueueAdmission,
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
        queue_state=cast(QueueState, admission.outcome.value),
        queue_position=admission.position,
        queue_deadline_at=admission.deadline_at,
    )


async def _admit_pending_job(
    repository: AnalysisJobRepository,
    admission: QueueAdmissionController,
    job_id: UUID,
    user_id: UUID,
    consent: bool,
) -> QueueAdmission:
    current = await admission.state(str(job_id))
    decision = current or await admission.admit(
        str(job_id), str(user_id), consent, int(time.time())
    )
    if decision.outcome is AdmissionOutcome.ACTIVE:
        job = await repository.get_by_id(job_id)
        if job is None:
            raise RuntimeError("admitted analysis job is missing")
        await repository.ensure_outbox(job.id, job.admission_correlation_id)
    audit_event_safely(
        "analysis_queue_transition",
        job_id=str(job_id),
        queue_transition=decision.outcome.value,
        queue_position=decision.position,
    )
    return decision


def _raise_admission_rejection(decision: QueueAdmission) -> None:
    if decision.outcome is AdmissionOutcome.QUEUE_FULL:
        raise ApiError(
            "analysis_queue_full",
            "Analysis capacity is currently unavailable.",
            429,
            retry_after=60,
        )
    if decision.outcome is AdmissionOutcome.USER_BUSY:
        raise ApiError("analysis_user_busy", "An analysis is already active or waiting.", 409)


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
    request: Request,
    response: Response,
    user: ExtensionIngestUserDep,
    session: SessionDep,
    before_commit: BeforeCommitHookDep,
    terminal_observer: IngestionTerminalObserverDep,
    admission: AdmissionDep,
) -> IngestionStatusResponse:
    service = CompletedGameIngestionService(
        session,
        require_source_checksum=request.app.state.settings.environment is Environment.PRODUCTION,
        enqueue_analysis=False,
    )

    async def ingest_and_admit() -> tuple[Game, AnalysisJob, QueueAdmission]:
        game = await service.ingest(user.id, payload)
        repository = AnalysisJobRepository(session)
        job = await repository.get_by_game_profile_version(game.id, "standard", 1)
        if job is None:
            raise RuntimeError("analysis job is missing after ingestion")
        if job.status is AnalysisJobStatus.PENDING:
            decision = await _admit_pending_job(
                repository, admission, job.id, user.id, payload.queue_consent
            )
            _raise_admission_rejection(decision)
        else:
            decision = QueueAdmission(AdmissionOutcome.ACTIVE)
        return game, job, decision

    try:
        game, job, decision = await execute_ingestion_attempt(
            execute=lambda: TransactionBoundary(session, before_commit).execute(ingest_and_admit),
            observer=terminal_observer,
            game_id_from_result=lambda result: result[0].id,
        )
    except IngestionConflictError as error:
        raise ApiError("ingestion_conflict", "Ingestion could not be completed.", 409) from error
    except ProvenanceValidationError as error:
        raise ApiError("provenance_rejected", "Source verification failed.", 422) from error
    except QueueAdmissionUnavailable as error:
        raise ApiError(
            "analysis_admission_unavailable",
            "Analysis admission is temporarily unavailable.",
            503,
            retry_after=60,
        ) from error
    response.headers["Cache-Control"] = "no-store"
    if decision.outcome is not AdmissionOutcome.ACTIVE:
        response.status_code = 202
    return response_from_game(
        game.id, game.status, game.normalized_moves, job.id, job.status, decision
    )


@router.post(
    "/analysis-jobs/{job_id}/queue-consent",
    response_model=QueueActionResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def consent_to_queue(
    job_id: UUID,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
    before_commit: BeforeCommitHookDep,
    admission: AdmissionDep,
) -> QueueActionResponse:
    repository = AnalysisJobRepository(session)

    async def consent() -> tuple[AnalysisJob, QueueAdmission]:
        job = await repository.get_owned_by_id(job_id, user.id)
        if job is None:
            raise ApiError("not_found", "The requested resource was not found.", 404)
        if job.status is not AnalysisJobStatus.PENDING:
            raise ApiError("queue_action_rejected", "Queue action is not available.", 409)
        decision = await _admit_pending_job(repository, admission, job.id, user.id, True)
        _raise_admission_rejection(decision)
        return job, decision

    try:
        job, decision = await TransactionBoundary(session, before_commit).execute(consent)
    except QueueAdmissionUnavailable as error:
        raise ApiError(
            "analysis_admission_unavailable",
            "Analysis admission is temporarily unavailable.",
            503,
            retry_after=60,
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return QueueActionResponse(
        analysis_job_id=job.id,
        analysis_job_status=job.status,
        queue_state=cast(QueueActionState, decision.outcome.value),
        queue_position=decision.position,
        queue_deadline_at=decision.deadline_at,
    )


@router.post(
    "/analysis-jobs/{job_id}/queue-cancel",
    response_model=QueueActionResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def cancel_waiting_job(
    job_id: UUID,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
    before_commit: BeforeCommitHookDep,
    admission: AdmissionDep,
) -> QueueActionResponse:
    job = await AnalysisJobRepository(session).get_owned_by_id(job_id, user.id)
    if job is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    try:
        removed = await admission.cancel_waiting(str(job.id), str(user.id))
    except QueueAdmissionUnavailable as error:
        raise ApiError(
            "analysis_admission_unavailable",
            "Analysis admission is temporarily unavailable.",
            503,
            retry_after=60,
        ) from error
    if not removed:
        raise ApiError("queue_action_rejected", "Queue action is not available.", 409)
    accepted = await AnalysisJobTerminalService(session).terminalize(
        job.id,
        AnalysisJobStatus.CANCELLED,
        "queue_cancelled_by_user",
        "Queued analysis was cancelled.",
        datetime.now(UTC),
        before_commit,
    )
    if not accepted:
        raise ApiError("queue_action_rejected", "Queue action is not available.", 409)
    response.headers["Cache-Control"] = "no-store"
    return QueueActionResponse(
        analysis_job_id=job.id,
        analysis_job_status=AnalysisJobStatus.CANCELLED,
        queue_state="CANCELLED",
    )


@router.post(
    "/analysis-jobs/{job_id}/queue-extend",
    response_model=QueueActionResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def extend_waiting_job(
    job_id: UUID,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
    admission: AdmissionDep,
) -> QueueActionResponse:
    job = await AnalysisJobRepository(session).get_owned_by_id(job_id, user.id)
    if job is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    try:
        extended = await admission.extend_wait(str(job.id), int(time.time()))
        current = await admission.state(str(job.id))
    except QueueAdmissionUnavailable as error:
        raise ApiError(
            "analysis_admission_unavailable",
            "Analysis admission is temporarily unavailable.",
            503,
            retry_after=60,
        ) from error
    if not extended or current is None or current.outcome is not AdmissionOutcome.WAITING:
        raise ApiError("queue_action_rejected", "Queue action is not available.", 409)
    audit_event_safely(
        "analysis_queue_transition",
        job_id=str(job.id),
        queue_transition="WAIT_EXTENDED",
        queue_position=current.position,
    )
    response.headers["Cache-Control"] = "no-store"
    return QueueActionResponse(
        analysis_job_id=job.id,
        analysis_job_status=job.status,
        queue_state="WAITING",
        queue_position=current.position,
        queue_deadline_at=current.deadline_at,
    )


@router.get(
    "/{game_id}/ingestion-status",
    response_model=IngestionStatusResponse,
    responses={401: {"model": ErrorResponse, "description": "Bearer authentication failed."}},
)
async def ingestion_status(
    game_id: UUID,
    request: Request,
    response: Response,
    user: ExtensionStatusUserDep,
    session: SessionDep,
    admission: AdmissionDep,
) -> IngestionStatusResponse:
    game = await CompletedGameIngestionService(session).get_for_user(game_id, user.id)
    if game is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    job = await AnalysisJobRepository(session).get_by_game_profile_version(game.id, "standard", 1)
    if job is None:
        raise ApiError("not_found", "The requested resource was not found.", 404)
    try:
        state = await admission.state(str(job.id))
    except QueueAdmissionUnavailable as error:
        raise ApiError(
            "analysis_admission_unavailable",
            "Analysis admission is temporarily unavailable.",
            503,
            retry_after=60,
        ) from error
    if state is None and job.status in {
        AnalysisJobStatus.SUCCEEDED,
        AnalysisJobStatus.FAILED,
        AnalysisJobStatus.CANCELLED,
    }:
        state = QueueAdmission(AdmissionOutcome.TERMINAL)
    return response_from_game(
        game.id,
        game.status,
        game.normalized_moves,
        job.id,
        job.status,
        state or QueueAdmission(AdmissionOutcome.CONSENT_REQUIRED),
    )
