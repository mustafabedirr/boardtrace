import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from boardtrace_api.models.enums import AnalysisJobStatus, GameResult, GameStatus, PlayerColor

UCI_MOVE_PATTERN = r"^[a-h][1-8][a-h][1-8][qrbn]?$"


class CompletedGameIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    platform: str = Field(min_length=1, max_length=100)
    source_game_id: str = Field(min_length=1, max_length=200)
    completed_at: datetime
    player_color: PlayerColor
    result: GameResult
    initial_fen: str | None = Field(default=None, max_length=100, repr=False)
    moves: list[str] = Field(min_length=1, max_length=600)

    @field_validator("platform", "source_game_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("moves")
    @classmethod
    def normalize_moves(cls, value: list[str]) -> list[str]:
        normalized = [move.strip().lower() for move in value]
        for move in normalized:
            if not re.fullmatch(UCI_MOVE_PATTERN, move):
                raise ValueError("moves must use normalized UCI notation")
        return normalized


class IngestionStatusResponse(BaseModel):
    id: UUID
    ingestion_state: Literal["ACCEPTED"]
    game_status: GameStatus
    analysis_release_state: Literal["LOCKED"]
    analysis_available: Literal[False]
    normalized_move_count: int
    analysis_job_id: UUID
    analysis_job_status: AnalysisJobStatus
