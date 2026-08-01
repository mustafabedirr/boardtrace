from datetime import datetime
from typing import Protocol
from uuid import UUID

from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.observability import (
    AnalysisMetrics,
    NoOpAnalysisMetrics,
    audit_event_safely,
    metric_gauge,
    metric_increment,
    metric_observe,
)
from boardtrace_api.analysis.queue import AnalysisQueue
from boardtrace_api.analysis.retry import JitterSource, RetryPolicy, ZeroJitter
from boardtrace_api.db.transactions import (
    BeforeCommitHook,
    TransactionBoundary,
    no_op_before_commit,
)
from boardtrace_api.models import AnalysisJob
from boardtrace_api.models.enums import AnalysisJobStatus, GameStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.repositories.games import GameRepository
from boardtrace_api.services.analysis_cleanup import (
    GameDataCleanup,
    TerminalGameDataCleanup,
    record_cleanup,
)


class AnalysisJobEligibilityError(ValueError):
    pass


class TerminalFailureRepository(Protocol):
    async def fail_job(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        now: datetime,
        lease_generation: int | None = None,
    ) -> bool: ...


class AnalysisJobService:
    def __init__(self, session: AsyncSession, metrics: AnalysisMetrics | None = None) -> None:
        self._session = session
        self._jobs = AnalysisJobRepository(session)
        self._metrics = metrics or NoOpAnalysisMetrics()

    async def create_for_completed_game(
        self, game_id: UUID, correlation_id: UUID, *, enqueue: bool = True
    ) -> AnalysisJob:
        game = await GameRepository(self._session).get_by_id(game_id)
        if (
            game is None
            or game.status != GameStatus.FINISHED
            or game.completion_verified_at is None
            or not game.normalized_moves
            or game.ingestion_payload_hash is None
            or game.analysis_available_at is not None
        ):
            raise AnalysisJobEligibilityError("game is not eligible for post-game analysis")
        job = await self._jobs.create_if_absent(
            game.id, game.user_id, correlation_id, enqueue=enqueue
        )
        audit_event_safely(
            "analysis_job_created",
            job_id=str(job.id),
            correlation_id=str(correlation_id),
            status=job.status.value,
            attempt_count=job.attempt_count,
        )
        if enqueue:
            audit_event_safely(
                "analysis_job_enqueue_requested",
                job_id=str(job.id),
                correlation_id=str(correlation_id),
                delivery_generation=0,
            )
        metric_increment(self._metrics, "analysis_jobs_created_total", status=job.status.value)
        if enqueue:
            metric_increment(self._metrics, "analysis_jobs_enqueue_requested_total")
        return job


class AnalysisJobTerminalFailureService:
    """Commits terminal failure mutations before emitting bounded observability."""

    def __init__(
        self,
        session: AsyncSession,
        metrics: AnalysisMetrics | None = None,
        repository: TerminalFailureRepository | None = None,
        cleanup: GameDataCleanup | None = None,
    ) -> None:
        self._session = session
        self._metrics = metrics or NoOpAnalysisMetrics()
        self._jobs = repository or AnalysisJobRepository(session)
        self._cleanup = cleanup or TerminalGameDataCleanup(session)

    async def fail_job(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        now: datetime,
        lease_generation: int | None = None,
        before_commit: BeforeCommitHook = no_op_before_commit,
    ) -> bool:
        cleaned = False

        async def fail_and_cleanup() -> bool:
            nonlocal cleaned
            accepted = await self._jobs.fail_job(
                job_id, worker_id, code, message, now, lease_generation
            )
            if accepted:
                cleaned = await self._cleanup.delete_for_job(job_id)
            return accepted

        accepted = await TransactionBoundary(self._session, before_commit).execute(fail_and_cleanup)
        if accepted:
            record_cleanup(job_id, "deleted" if cleaned else "already_absent")
            audit_event_safely(
                "analysis_job_failed",
                job_id=str(job_id),
                worker_id=worker_id,
                status="FAILED",
                error_code=code,
            )
            metric_increment(
                self._metrics,
                "analysis_jobs_failed_total",
                status="FAILED",
                error_code=code[:100],
            )
        else:
            audit_event_safely(
                "analysis_job_invalid_transition_rejected",
                job_id=str(job_id),
                worker_id=worker_id,
                error_code="terminal_failure_rejected",
            )
            metric_increment(
                self._metrics,
                "analysis_job_invalid_transitions_total",
                error_code="terminal_failure_rejected",
            )
        return accepted


class AnalysisJobTerminalService:
    """One cleanup transaction for non-owner worker loss, expiry and cancellation."""

    def __init__(
        self,
        session: AsyncSession,
        metrics: AnalysisMetrics | None = None,
        cleanup: GameDataCleanup | None = None,
    ) -> None:
        self._session = session
        self._metrics = metrics or NoOpAnalysisMetrics()
        self._jobs = AnalysisJobRepository(session)
        self._cleanup = cleanup or TerminalGameDataCleanup(session)

    async def terminalize(
        self,
        job_id: UUID,
        target: AnalysisJobStatus,
        code: str,
        message: str,
        now: datetime,
        before_commit: BeforeCommitHook = no_op_before_commit,
    ) -> bool:
        cleaned = False

        async def mutate_and_cleanup() -> bool:
            nonlocal cleaned
            accepted = await self._jobs.terminalize_job(job_id, target, code, message, now)
            if accepted:
                cleaned = await self._cleanup.delete_for_job(job_id)
            return accepted

        accepted = await TransactionBoundary(self._session, before_commit).execute(
            mutate_and_cleanup
        )
        if accepted:
            record_cleanup(job_id, "deleted" if cleaned else "already_absent")
            audit_event_safely(
                "analysis_job_terminalized",
                job_id=str(job_id),
                status=target.value,
                error_code=code,
                cleanup_result="deleted" if cleaned else "already_absent",
            )
            metric_increment(
                self._metrics,
                "analysis_jobs_cancelled_total"
                if target is AnalysisJobStatus.CANCELLED
                else "analysis_jobs_failed_total",
                status=target.value,
                error_code=code[:100],
            )
        return accepted


class OutboxPublisher:
    def __init__(
        self, session: AsyncSession, queue: AnalysisQueue, metrics: AnalysisMetrics | None = None
    ) -> None:
        self._session = session
        self._queue = queue
        self._jobs = AnalysisJobRepository(session)
        self._metrics = metrics or NoOpAnalysisMetrics()
        self._retry_policy = RetryPolicy(30, 900, 0)
        self._jitter: JitterSource = ZeroJitter()

    async def publish_due(self, now: datetime, limit: int = 100) -> int:
        published = 0
        for event in await self._jobs.list_publishable_outbox(now, limit):
            started_at = datetime.now(now.tzinfo)
            try:
                message_id = self._queue.enqueue_analysis_job(
                    event.analysis_job_id, event.correlation_id
                )
            except (ConnectionError, TimeoutError, KombuOperationalError):
                self._jobs.record_outbox_failure(
                    event,
                    "queue_temporarily_unavailable",
                    now
                    + self._retry_policy.delay_for_attempt(event.attempt_count + 1, self._jitter),
                )
                audit_event_safely(
                    "analysis_job_publish_failed",
                    job_id=str(event.analysis_job_id),
                    correlation_id=str(event.correlation_id),
                    error_code="queue_temporarily_unavailable",
                )
                metric_increment(
                    self._metrics,
                    "analysis_jobs_publish_failed_total",
                    error_code="queue_temporarily_unavailable",
                )
            else:
                await self._jobs.mark_outbox_published(event, message_id, now)
                audit_event_safely(
                    "analysis_job_published",
                    job_id=str(event.analysis_job_id),
                    correlation_id=str(event.correlation_id),
                    delivery_generation=event.delivery_generation,
                )
                metric_increment(self._metrics, "analysis_jobs_published_total")
                published += 1
            metric_observe(
                self._metrics,
                "analysis_outbox_publish_duration_seconds",
                max(0.0, (datetime.now(now.tzinfo) - started_at).total_seconds()),
            )
        inflight, pending = await self._jobs.observability_snapshot()
        metric_gauge(self._metrics, "analysis_jobs_inflight", inflight)
        metric_gauge(self._metrics, "analysis_outbox_pending", pending)
        return published
