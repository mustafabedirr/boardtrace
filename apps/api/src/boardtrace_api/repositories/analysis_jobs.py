from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.retry import JitterSource, RetryPolicy, ZeroJitter
from boardtrace_api.analysis.state import TERMINAL_STATUSES, validate_transition
from boardtrace_api.models import AnalysisJob, AnalysisJobOutbox
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisJobType, AnalysisOutboxStatus

ENQUEUE_EVENT = "ANALYSIS_JOB_ENQUEUE"


class AnalysisJobRepository:
    """Typed persistence operations; callers own every transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _owns_lease(job: AnalysisJob, worker_id: str, lease_generation: int | None) -> bool:
        return job.worker_id == worker_id and (
            lease_generation is None or job.lease_generation == lease_generation
        )

    async def get_by_id(self, job_id: UUID, *, lock: bool = False) -> AnalysisJob | None:
        statement = select(AnalysisJob).where(AnalysisJob.id == job_id)
        if lock:
            statement = statement.with_for_update()
        return cast(AnalysisJob | None, await self._session.scalar(statement))

    async def get_owned_by_id(self, job_id: UUID, owner_user_id: UUID) -> AnalysisJob | None:
        return cast(
            AnalysisJob | None,
            await self._session.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.id == job_id, AnalysisJob.owner_user_id == owner_user_id
                )
            ),
        )

    async def get_by_game_profile_version(
        self, game_id: UUID, profile: str, version: int
    ) -> AnalysisJob | None:
        return cast(
            AnalysisJob | None,
            await self._session.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.game_id == game_id,
                    AnalysisJob.analysis_profile == profile,
                    AnalysisJob.analysis_version == version,
                )
            ),
        )

    async def create_if_absent(
        self, game_id: UUID, owner_user_id: UUID, correlation_id: UUID
    ) -> AnalysisJob:
        existing = await self.get_by_game_profile_version(game_id, "standard", 1)
        if existing is not None:
            return existing
        proposed_id = uuid4()
        inserted_id = await self._session.scalar(
            insert(AnalysisJob)
            .values(
                id=proposed_id,
                game_id=game_id,
                owner_user_id=owner_user_id,
                position_id=None,
                job_type=AnalysisJobType.REPORT,
                status=AnalysisJobStatus.PENDING,
                attempts=0,
                attempt_count=0,
                max_attempts=3,
                analysis_profile="standard",
                analysis_version=1,
            )
            .on_conflict_do_nothing(
                index_elements=["game_id", "analysis_profile", "analysis_version"]
            )
            .returning(AnalysisJob.id)
        )
        job_id = cast(
            UUID,
            inserted_id
            or await self._session.scalar(
                select(AnalysisJob.id).where(
                    AnalysisJob.game_id == game_id,
                    AnalysisJob.analysis_profile == "standard",
                    AnalysisJob.analysis_version == 1,
                )
            ),
        )
        await self._session.execute(
            insert(AnalysisJobOutbox)
            .values(
                id=uuid4(),
                analysis_job_id=job_id,
                event_type=ENQUEUE_EVENT,
                payload_version=1,
                delivery_generation=0,
                correlation_id=correlation_id,
                status=AnalysisOutboxStatus.PENDING,
                attempt_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "analysis_job_id",
                    "event_type",
                    "payload_version",
                    "delivery_generation",
                ]
            )
        )
        job = await self.get_by_id(job_id)
        if job is None:
            raise RuntimeError("analysis job insert did not return a persistent row")
        return job

    async def list_publishable_outbox(self, now: datetime, limit: int) -> list[AnalysisJobOutbox]:
        rows = await self._session.scalars(
            select(AnalysisJobOutbox)
            .where(
                AnalysisJobOutbox.status == AnalysisOutboxStatus.PENDING,
                (AnalysisJobOutbox.next_attempt_at.is_(None))
                | (AnalysisJobOutbox.next_attempt_at <= now),
            )
            .order_by(AnalysisJobOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows)

    async def mark_outbox_published(
        self, outbox: AnalysisJobOutbox, message_id: str, now: datetime
    ) -> None:
        outbox.status = AnalysisOutboxStatus.PUBLISHED
        outbox.published_at = now
        job = await self.get_by_id(outbox.analysis_job_id, lock=True)
        if job is not None and job.status in {
            AnalysisJobStatus.PENDING,
            AnalysisJobStatus.RETRY_SCHEDULED,
        }:
            validate_transition(job.status, AnalysisJobStatus.QUEUED)
            job.status = AnalysisJobStatus.QUEUED
            job.queued_at = now
            job.queue_message_id = message_id[:255]

    def record_outbox_failure(
        self, outbox: AnalysisJobOutbox, code: str, next_attempt_at: datetime
    ) -> None:
        outbox.attempt_count += 1
        outbox.last_error_code = code[:100]
        outbox.next_attempt_at = next_attempt_at

    async def create_retry_outbox_if_absent(self, job: AnalysisJob, correlation_id: UUID) -> None:
        await self._session.execute(
            insert(AnalysisJobOutbox)
            .values(
                id=uuid4(),
                analysis_job_id=job.id,
                event_type=ENQUEUE_EVENT,
                payload_version=1,
                delivery_generation=job.attempt_count,
                correlation_id=correlation_id,
                status=AnalysisOutboxStatus.PENDING,
                attempt_count=0,
                next_attempt_at=job.next_attempt_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "analysis_job_id",
                    "event_type",
                    "payload_version",
                    "delivery_generation",
                ]
            )
        )

    async def claim_job(
        self, job_id: UUID, worker_id: str, now: datetime, lease_seconds: int
    ) -> AnalysisJob | None:
        job = await self.get_by_id(job_id, lock=True)
        if job is None or job.status != AnalysisJobStatus.QUEUED:
            return None
        validate_transition(job.status, AnalysisJobStatus.CLAIMED)
        job.status = AnalysisJobStatus.CLAIMED
        job.claimed_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.worker_id = worker_id[:255]
        job.lease_generation += 1
        job.attempt_count += 1
        job.attempts = job.attempt_count
        return job

    async def start_job(
        self, job_id: UUID, worker_id: str, now: datetime, lease_generation: int | None = None
    ) -> bool:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status != AnalysisJobStatus.CLAIMED
            or not self._owns_lease(job, worker_id, lease_generation)
        ):
            return False
        validate_transition(job.status, AnalysisJobStatus.RUNNING)
        job.status = AnalysisJobStatus.RUNNING
        job.started_at = now
        return True

    async def heartbeat_job(
        self,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
        lease_generation: int | None = None,
    ) -> bool:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status not in {AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING}
            or not self._owns_lease(job, worker_id, lease_generation)
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            return False
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        return True

    async def complete_job(
        self, job_id: UUID, worker_id: str, now: datetime, lease_generation: int | None = None
    ) -> bool:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status != AnalysisJobStatus.RUNNING
            or not self._owns_lease(job, worker_id, lease_generation)
        ):
            return False
        validate_transition(job.status, AnalysisJobStatus.SUCCEEDED)
        job.status = AnalysisJobStatus.SUCCEEDED
        job.completed_at = now
        job.finished_at = now
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        return True

    async def schedule_retry(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        when: datetime,
        correlation_id: UUID,
        lease_generation: int | None = None,
    ) -> bool:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status not in {AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING}
            or not self._owns_lease(job, worker_id, lease_generation)
        ):
            return False
        validate_transition(job.status, AnalysisJobStatus.RETRY_SCHEDULED)
        job.status = AnalysisJobStatus.RETRY_SCHEDULED
        job.next_attempt_at = when
        job.attempt_count += 1
        job.attempts = job.attempt_count
        job.last_error_code = code[:100]
        job.last_error_message = message[:500]
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        await self.create_retry_outbox_if_absent(job, correlation_id)
        return True

    async def fail_job(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        now: datetime,
        lease_generation: int | None = None,
    ) -> bool:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status in TERMINAL_STATUSES
            or not self._owns_lease(job, worker_id, lease_generation)
        ):
            return False
        validate_transition(job.status, AnalysisJobStatus.FAILED)
        job.status = AnalysisJobStatus.FAILED
        job.failed_at = now
        job.finished_at = now
        job.last_error_code = code[:100]
        job.last_error_message = message[:500]
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        return True

    async def recover_expired_lease(
        self,
        job_id: UUID,
        now: datetime,
        retry_policy: RetryPolicy,
        jitter: JitterSource | None = None,
        correlation_id: UUID | None = None,
    ) -> AnalysisJob | None:
        job = await self.get_by_id(job_id, lock=True)
        if (
            job is None
            or job.status not in {AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING}
            or job.lease_expires_at is None
            or job.lease_expires_at > now
        ):
            return None
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        if job.attempt_count >= job.max_attempts:
            validate_transition(job.status, AnalysisJobStatus.FAILED)
            job.status = AnalysisJobStatus.FAILED
            job.failed_at = now
            job.last_error_code = "lease_attempts_exhausted"
        else:
            validate_transition(job.status, AnalysisJobStatus.RETRY_SCHEDULED)
            job.status = AnalysisJobStatus.RETRY_SCHEDULED
            job.attempt_count += 1
            job.attempts = job.attempt_count
            job.next_attempt_at = now + retry_policy.delay_for_attempt(
                job.attempt_count, jitter or ZeroJitter()
            )
            job.last_error_code = "lease_expired"
            await self.create_retry_outbox_if_absent(job, correlation_id or uuid4())
        return job

    async def get_safe_status(self, job_id: UUID, owner_user_id: UUID) -> AnalysisJob | None:
        return await self.get_owned_by_id(job_id, owner_user_id)

    async def observability_snapshot(self) -> tuple[int, int]:
        """Return authoritative gauges from PostgreSQL, never process-local counters."""
        inflight = await self._session.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.status.in_((AnalysisJobStatus.CLAIMED, AnalysisJobStatus.RUNNING)))
        )
        pending = await self._session.scalar(
            select(func.count())
            .select_from(AnalysisJobOutbox)
            .where(
                AnalysisJobOutbox.status == AnalysisOutboxStatus.PENDING,
                AnalysisJobOutbox.published_at.is_(None),
            )
        )
        return int(inflight or 0), int(pending or 0)


def utc_now() -> datetime:
    return datetime.now(UTC)
