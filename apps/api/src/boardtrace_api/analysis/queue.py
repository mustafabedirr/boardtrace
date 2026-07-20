from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

ANALYSIS_QUEUE = "boardtrace.analysis.jobs"
ANALYSIS_TASK = "boardtrace.analysis.run"
OUTBOX_PUBLISH_TASK = "boardtrace.analysis.publish-outbox"


class AnalysisTaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    job_id: UUID
    correlation_id: UUID

    @field_validator("schema_version")
    @classmethod
    def supported_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported schema version")
        return value


class AnalysisQueue(Protocol):
    def enqueue_analysis_job(self, job_id: UUID, correlation_id: UUID) -> str: ...
