from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from datetime import UTC, datetime
from uuid import UUID

from celery import Celery, Task
from celery.exceptions import TimeLimitExceeded, WorkerLostError
from celery.signals import task_failure
from kombu import Queue
from pydantic import ValidationError
from redis.asyncio import Redis

from boardtrace_api.analysis.celery_adapter import CeleryAnalysisQueue
from boardtrace_api.analysis.failures import classify_failure
from boardtrace_api.analysis.full_game import (
    CompletedGameAnalysisInput,
    EngineReusePolicy,
    FullGameAnalysisBudget,
    FullGameAnalyzer,
)
from boardtrace_api.analysis.observability import (
    NoOpAnalysisMetrics,
    audit_event_safely,
    metric_increment,
    metric_observe,
)
from boardtrace_api.analysis.queue import (
    ANALYSIS_QUEUE,
    ANALYSIS_TASK,
    OUTBOX_PUBLISH_TASK,
    AnalysisTaskPayload,
)
from boardtrace_api.analysis.retry import RetryPolicy, ZeroJitter
from boardtrace_api.analysis.stockfish import StockfishEngine
from boardtrace_api.config import Settings
from boardtrace_api.db.engine import create_database_engine
from boardtrace_api.db.session import create_session_factory
from boardtrace_api.models import Game
from boardtrace_api.models.enums import AnalysisJobStatus
from boardtrace_api.queue_admission import QueueAdmissionUnavailable, RedisQueueAdmission
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.services.analysis_jobs import (
    AnalysisJobTerminalFailureService,
    AnalysisJobTerminalService,
    OutboxPublisher,
)
from boardtrace_api.services.analysis_results import (
    AnalysisResultPersistenceService,
    EngineConfigurationSnapshot,
)

logger = logging.getLogger(__name__)
settings = Settings()
metrics = NoOpAnalysisMetrics()


def _wait_for_test_gate() -> None:
    """Pause only a worker explicitly launched by the runtime test harness."""
    gate_path = os.environ.get("BOARDTRACE_TEST_WORKER_GATE_PATH")
    if not gate_path or os.environ.get("BOARDTRACE_TEST_WORKER_GATE_ENABLED") != "1":
        return
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if os.path.exists(gate_path):
            return
        time.sleep(0.05)
    raise ValueError("test worker gate timed out")


celery_app = Celery("boardtrace-analysis", broker=str(settings.redis_url), backend=None)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    enable_utc=True,
    timezone="UTC",
    task_default_queue=ANALYSIS_QUEUE,
    task_queues=(Queue(ANALYSIS_QUEUE),),
    task_routes={
        ANALYSIS_TASK: {"queue": ANALYSIS_QUEUE},
        OUTBOX_PUBLISH_TASK: {"queue": ANALYSIS_QUEUE},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    task_soft_time_limit=settings.analysis_task_soft_time_limit_seconds,
    task_time_limit=settings.analysis_task_time_limit_seconds,
    task_ignore_result=True,
    beat_schedule={
        "publish-analysis-outbox": {
            "task": OUTBOX_PUBLISH_TASK,
            "schedule": 5.0,
        },
        "sweep-analysis-lifecycle": {
            "task": "boardtrace.analysis.sweep-lifecycle",
            "schedule": 5.0,
        },
    },
)


async def _run_analysis(payload: AnalysisTaskPayload, worker_id: str) -> str:
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        now = datetime.now(UTC)
        async with session_factory() as session:
            repository = AnalysisJobRepository(session)
            job = await repository.claim_job(
                payload.job_id, worker_id, now, settings.analysis_lease_seconds
            )
            await session.commit()
            if job is None:
                audit_event_safely(
                    "analysis_job_duplicate_delivery_ignored", job_id=str(payload.job_id)
                )
                metric_increment(metrics, "analysis_job_duplicate_deliveries_total")
                return "duplicate_or_ineligible"
            audit_event_safely(
                "analysis_job_claimed",
                job_id=str(payload.job_id),
                worker_id=worker_id,
                status="CLAIMED",
                attempt_count=job.attempt_count,
            )
            metric_increment(metrics, "analysis_jobs_claimed_total")
            lease_generation = job.lease_generation
        async with session_factory() as session:
            repository = AnalysisJobRepository(session)
            if not await repository.start_job(
                payload.job_id, worker_id, datetime.now(UTC), lease_generation
            ):
                await session.rollback()
                return "claim_lost"
            await session.commit()
            audit_event_safely(
                "analysis_job_started", job_id=str(payload.job_id), worker_id=worker_id
            )
            metric_increment(metrics, "analysis_jobs_started_total")
        try:
            _wait_for_test_gate()
            async with session_factory() as session:
                current = await AnalysisJobRepository(session).get_by_id(payload.job_id)
                if (
                    current is None
                    or current.status is not AnalysisJobStatus.RUNNING
                    or current.worker_id != worker_id
                    or current.lease_generation != lease_generation
                    or current.lease_expires_at is None
                    or current.lease_expires_at <= datetime.now(UTC)
                ):
                    return "execution_authority_rejected"
                game = await session.get(Game, current.game_id)
                if game is None:
                    raise LookupError("analysis game is missing")
                completed_game = CompletedGameAnalysisInput(
                    game_id=game.id,
                    game_status=game.status,
                    completion_verified_at=game.completion_verified_at,
                    initial_fen=game.initial_fen,
                    normalized_moves_uci=tuple(game.normalized_moves or ()),
                )
            analysis_started_at = datetime.now(UTC)
            result = FullGameAnalyzer(
                StockfishEngine(
                    settings.stockfish_path,
                    settings.stockfish_threads,
                    settings.stockfish_hash_mb,
                    settings.stockfish_timeout_seconds,
                )
            ).analyse(completed_game, _analysis_budget())
            analysis_finished_at = datetime.now(UTC)
            async with session_factory() as session:
                await AnalysisResultPersistenceService(
                    session
                ).persist_and_complete_owned_generation(
                    job_id=payload.job_id,
                    worker_id=worker_id,
                    lease_generation=lease_generation,
                    result=result,
                    configuration=_configuration_snapshot(),
                    started_at=analysis_started_at,
                    finished_at=analysis_finished_at,
                )
                audit_event_safely(
                    "analysis_job_succeeded", job_id=str(payload.job_id), worker_id=worker_id
                )
                metric_increment(metrics, "analysis_jobs_succeeded_total")
                metric_observe(
                    metrics,
                    "analysis_job_duration_seconds",
                    (analysis_finished_at - analysis_started_at).total_seconds(),
                )
                await _release_capacity(payload.job_id, job.owner_user_id)
                return "completed"
        except Exception as error:
            decision = classify_failure(error)
            if not decision.retryable or not settings.analysis_automatic_retry_enabled:
                async with session_factory() as session:
                    failed = await AnalysisJobTerminalFailureService(session, metrics).fail_job(
                        payload.job_id,
                        worker_id,
                        decision.code,
                        decision.message,
                        datetime.now(UTC),
                        lease_generation,
                    )
                if failed:
                    await _release_capacity(payload.job_id, job.owner_user_id)
                return "failed" if failed else "failure_rejected"
            now = datetime.now(UTC)
            retry_at = now + RetryPolicy(30, 900, 0).delay_for_attempt(
                job.attempt_count + 1, ZeroJitter()
            )
            async with session_factory() as session:
                scheduled = await AnalysisJobRepository(session).schedule_retry(
                    payload.job_id,
                    worker_id,
                    decision.code,
                    decision.message,
                    retry_at,
                    payload.correlation_id,
                    lease_generation,
                )
                await session.commit()
            return "retry_scheduled" if scheduled else "retry_rejected"
    finally:
        await engine.dispose()


def _analysis_budget() -> FullGameAnalysisBudget:
    return FullGameAnalysisBudget(
        depth=settings.analysis_depth,
        max_position_time_ms=settings.analysis_max_position_time_ms,
        max_moves=settings.analysis_max_moves,
        max_positions=settings.analysis_max_positions,
        max_game_time_ms=settings.analysis_max_game_time_ms,
    )


def _configuration_snapshot() -> EngineConfigurationSnapshot:
    return EngineConfigurationSnapshot(
        schema_version=1,
        depth=settings.analysis_depth,
        max_position_time_ms=settings.analysis_max_position_time_ms,
        max_game_time_ms=settings.analysis_max_game_time_ms,
        max_positions=settings.analysis_max_positions,
        max_moves=settings.analysis_max_moves,
        threads=settings.stockfish_threads,
        hash_mb=settings.stockfish_hash_mb,
        command_timeout_ms=round(settings.stockfish_timeout_seconds * 1000),
        reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
    )


async def _publish_outbox() -> int:
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            count = await OutboxPublisher(
                session, CeleryAnalysisQueue(celery_app), metrics
            ).publish_due(datetime.now(UTC))
            await session.commit()
            return count
    finally:
        await engine.dispose()


async def _release_capacity(job_id: UUID, owner_user_id: UUID) -> None:
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        promoted = await RedisQueueAdmission(redis).complete_active(str(job_id), str(owner_user_id))
        if promoted is None:
            return
        promoted_id = UUID(promoted)
        engine = create_database_engine(settings)
        session_factory = create_session_factory(engine)
        try:
            async with session_factory() as session:
                repository = AnalysisJobRepository(session)
                promoted_job = await repository.get_by_id(promoted_id, lock=True)
                if promoted_job is None or promoted_job.status is not AnalysisJobStatus.PENDING:
                    await session.rollback()
                    return
                await repository.ensure_outbox(
                    promoted_job.id, promoted_job.admission_correlation_id
                )
                await session.commit()
                audit_event_safely(
                    "analysis_queue_transition",
                    job_id=str(promoted_job.id),
                    queue_transition="PROMOTED_ACTIVE",
                )
        finally:
            await engine.dispose()
    except QueueAdmissionUnavailable:
        audit_event_safely(
            "analysis_queue_transition",
            job_id=str(job_id),
            queue_transition="RELEASE_DEFERRED_REDIS_UNAVAILABLE",
        )
    finally:
        await redis.aclose()


async def _terminalize_external_failure(job_id: UUID, code: str) -> bool:
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            job = await AnalysisJobRepository(session).get_by_id(job_id)
            if job is None:
                return False
            owner_user_id = job.owner_user_id
            accepted = await AnalysisJobTerminalService(session, metrics).terminalize(
                job_id,
                AnalysisJobStatus.FAILED,
                code,
                "Analysis terminated before a valid result was committed.",
                datetime.now(UTC),
            )
        if accepted:
            await _release_capacity(job_id, owner_user_id)
        return accepted
    finally:
        await engine.dispose()


async def _sweep_lifecycle() -> int:
    now = datetime.now(UTC)
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    terminalized = 0
    try:
        admission = RedisQueueAdmission(redis)
        terminalized += await _expire_waiting_jobs(admission, int(now.timestamp()))
        async with session_factory() as session:
            expired_active = await AnalysisJobRepository(session).list_expired_active_jobs(now)
        for job_id in expired_active:
            if await _terminalize_external_failure(job_id, "worker_lease_expired"):
                terminalized += 1
        return terminalized
    finally:
        await redis.aclose()
        await engine.dispose()


async def _expire_waiting_jobs(admission: RedisQueueAdmission, now_epoch: int) -> int:
    terminalized = 0
    for raw_job_id in await admission.expire_waiting(now_epoch):
        if await _terminalize_external_failure(UUID(raw_job_id), "queue_wait_expired"):
            terminalized += 1
    return terminalized


@celery_app.task(name=OUTBOX_PUBLISH_TASK)
def publish_analysis_outbox() -> int:
    return asyncio.run(_publish_outbox())


@celery_app.task(name="boardtrace.analysis.sweep-lifecycle")
def sweep_analysis_lifecycle() -> int:
    return asyncio.run(_sweep_lifecycle())


@celery_app.task(name=ANALYSIS_TASK, bind=True)
def run_analysis_job(task: Task[..., str], payload: dict[str, object]) -> str:
    try:
        validated = AnalysisTaskPayload.model_validate(payload)
    except ValidationError:
        audit_event_safely("analysis_job_payload_rejected", error_code="invalid_task_payload")
        metric_increment(metrics, "analysis_job_payload_rejections_total")
        return "payload_rejected"
    request = task.request
    hostname = str(getattr(request, "hostname", socket.gethostname()))
    logger.info(
        "analysis job task received",
        extra={"job_id": str(validated.job_id), "correlation_id": str(validated.correlation_id)},
    )
    return asyncio.run(_run_analysis(validated, hostname))


@task_failure.connect
def terminalize_hard_worker_failure(
    sender: object | None = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[object, ...] | None = None,
    **_: object,
) -> None:
    if getattr(sender, "name", None) != ANALYSIS_TASK or not isinstance(
        exception, (TimeLimitExceeded, WorkerLostError)
    ):
        return
    raw_payload = args[0] if args else None
    try:
        payload = AnalysisTaskPayload.model_validate(raw_payload)
    except ValidationError:
        audit_event_safely("analysis_job_payload_rejected", error_code="invalid_failure_payload")
        return
    asyncio.run(_terminalize_external_failure(payload.job_id, "worker_hard_timeout_or_loss"))
