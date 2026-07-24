"""Public, immutable post-game analysis response contract."""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PublicMoveColor(StrEnum):
    WHITE = "WHITE"
    BLACK = "BLACK"


class PublicMoveQuality(StrEnum):
    BEST = "BEST"
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    INACCURACY = "INACCURACY"
    MISTAKE = "MISTAKE"
    BLUNDER = "BLUNDER"
    UNCLASSIFIED = "UNCLASSIFIED"


class PublicAnalysisDto(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicMoveAnalysis(PublicAnalysisDto):
    ply: int
    move_uci: str
    move_san: str
    mover: PublicMoveColor
    quality: PublicMoveQuality
    centipawn_loss: int | None


class PublicMoveQualityCount(PublicAnalysisDto):
    quality: PublicMoveQuality
    count: int


class PublicPlayerAnalysis(PublicAnalysisDto):
    color: PublicMoveColor
    total_move_count: int
    cpl_eligible_move_count: int
    excluded_move_count: int
    cpl_coverage: Decimal | None
    acpl: Decimal | None
    accuracy: Decimal | None
    classified_move_count: int
    unclassified_move_count: int
    classification_coverage: Decimal | None
    quality_counts: tuple[PublicMoveQualityCount, ...]


class PublicGameAnalysisResponse(PublicAnalysisDto):
    game_id: UUID
    moves: tuple[PublicMoveAnalysis, ...]
    white: PublicPlayerAnalysis
    black: PublicPlayerAnalysis
