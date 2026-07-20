from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from boardtrace_api.models.enums import AnalysisJobStatus


class AnalysisJobStatusResponse(BaseModel):
    job_id: UUID
    game_id: UUID
    status: AnalysisJobStatus
    attempt_count: int
    max_attempts: int
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    next_attempt_at: datetime | None
    analysis_available: Literal[False] = False
