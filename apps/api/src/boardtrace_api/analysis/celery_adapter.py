from uuid import UUID

from celery import Celery

from boardtrace_api.analysis.queue import ANALYSIS_QUEUE, ANALYSIS_TASK


class CeleryAnalysisQueue:
    def __init__(self, app: Celery) -> None:
        self._app = app

    def enqueue_analysis_job(self, job_id: UUID, correlation_id: UUID) -> str:
        result = self._app.send_task(
            ANALYSIS_TASK,
            kwargs={
                "payload": {
                    "schema_version": 1,
                    "job_id": str(job_id),
                    "correlation_id": str(correlation_id),
                }
            },
            queue=ANALYSIS_QUEUE,
        )
        return str(result.id)
