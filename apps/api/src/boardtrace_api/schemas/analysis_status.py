"""Bounded public readiness contract for post-game analysis polling."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PublicAnalysisReadiness(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"


class PublicPollingGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    should_retry: bool
    retry_after_ms: Literal[2000, 3000, 5000] | None
    minimum_interval_ms: Literal[2000]
    maximum_interval_ms: Literal[15000]
    backoff_multiplier: Annotated[float, Field(ge=1.5, le=1.5)]


class PublicAnalysisStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    game_id: UUID
    readiness: PublicAnalysisReadiness
    result_available: bool
    polling: PublicPollingGuidance
