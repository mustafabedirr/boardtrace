"""Owner-safe authoritative game lifecycle response."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from boardtrace_api.models.enums import GameStatus


class PublicGameLifecycleResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    game_id: UUID
    lifecycle: GameStatus
    completion_verified: bool
