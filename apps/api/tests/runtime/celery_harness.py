"""Function-scoped Celery resources for isolated runtime-test migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from celery import Celery
from kombu import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.celery_adapter import CeleryAnalysisQueue
from boardtrace_api.analysis.queue import ANALYSIS_QUEUE, ANALYSIS_TASK, OUTBOX_PUBLISH_TASK
from boardtrace_api.services.analysis_jobs import OutboxPublisher


@dataclass
class RuntimeCeleryHarness:
    """Owns one test-local Celery app and its publisher wiring."""

    app: Celery
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(cls, broker_url: str) -> RuntimeCeleryHarness:
        app = Celery(f"boardtrace-runtime-{uuid4().hex}", broker=broker_url, backend=None)
        app.conf.update(
            accept_content=["json"],
            task_serializer="json",
            result_serializer="json",
            task_default_queue=ANALYSIS_QUEUE,
            task_queues=(Queue(ANALYSIS_QUEUE),),
            task_routes={
                ANALYSIS_TASK: {"queue": ANALYSIS_QUEUE},
                OUTBOX_PUBLISH_TASK: {"queue": ANALYSIS_QUEUE},
            },
            task_ignore_result=True,
        )
        return cls(app)

    def queue(self) -> CeleryAnalysisQueue:
        self._require_open()
        return CeleryAnalysisQueue(self.app)

    def publisher(self, session: AsyncSession) -> OutboxPublisher:
        self._require_open()
        return OutboxPublisher(session, self.queue())

    def close(self) -> None:
        if self._closed:
            return
        self.app.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Runtime Celery harness is closed")
