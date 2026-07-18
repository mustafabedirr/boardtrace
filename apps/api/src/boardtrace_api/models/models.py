from datetime import datetime
from enum import Enum as PythonEnum
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from boardtrace_api.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from boardtrace_api.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
    AnalysisType,
    GameResult,
    GameStatus,
    PlayerColor,
    PositionValidationStatus,
)


def enum_type(enum_class: type[PythonEnum], name: str) -> Enum:
    return Enum(enum_class, name=name, native_enum=True, create_constraint=True)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    games: Mapped[list["Game"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "auth_sessions"
    token_digest: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="SET NULL")
    )
    user: Mapped[User] = relationship(back_populates="auth_sessions")


class ExtensionPairing(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "extension_pairings"
    code_digest: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    extension_id: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list[str]] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Game(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", "source_game_id", name="uq_games_user_platform_source_game_id"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[GameStatus] = mapped_column(enum_type(GameStatus, "game_status"), index=True)
    platform: Mapped[str] = mapped_column(String(100))
    player_color: Mapped[PlayerColor] = mapped_column(enum_type(PlayerColor, "player_color"))
    result: Mapped[GameResult] = mapped_column(enum_type(GameResult, "game_result"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_fen: Mapped[str | None] = mapped_column(Text())
    source_game_id: Mapped[str | None] = mapped_column(String(200))
    ingestion_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    ingestion_payload_hash: Mapped[str | None] = mapped_column(String(64))
    normalized_moves: Mapped[list[str] | None] = mapped_column(JSONB)
    completion_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="games")
    frames: Mapped[list["GameFrame"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    positions: Mapped[list["Position"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GameFrame(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "game_frames"
    __table_args__ = (UniqueConstraint("game_id", "sequence"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    game: Mapped[Game] = relationship(back_populates="frames")


class Position(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("game_id", "ply"),
        CheckConstraint(
            "detection_confidence >= 0 AND detection_confidence <= 1",
            name="detection_confidence_range",
        ),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    frame_id: Mapped[UUID | None] = mapped_column(ForeignKey("game_frames.id", ondelete="SET NULL"))
    ply: Mapped[int] = mapped_column(Integer)
    piece_placement: Mapped[str] = mapped_column(String(71))
    fen: Mapped[str | None] = mapped_column(Text())
    side_to_move: Mapped[Literal["w", "b"] | None] = mapped_column(String(1))
    castling_rights: Mapped[str | None] = mapped_column(String(4))
    en_passant: Mapped[str | None] = mapped_column(String(2))
    halfmove_clock: Mapped[int | None] = mapped_column(Integer)
    fullmove_number: Mapped[int | None] = mapped_column(Integer)
    detection_confidence: Mapped[float] = mapped_column()
    validation_status: Mapped[PositionValidationStatus] = mapped_column(
        enum_type(PositionValidationStatus, "position_validation_status")
    )
    game: Mapped[Game] = relationship(back_populates="positions")


class DetectedMove(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "detected_moves"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[UUID] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"), unique=True
    )
    previous_position_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL")
    )
    uci: Mapped[str | None] = mapped_column(String(5))
    san: Mapped[str | None] = mapped_column(String(20))
    from_square: Mapped[str | None] = mapped_column(String(2))
    to_square: Mapped[str | None] = mapped_column(String(2))
    promotion: Mapped[str | None] = mapped_column(String(1))
    is_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column()


class EngineAnalysis(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "engine_analyses"
    __table_args__ = (UniqueConstraint("position_id", "analysis_type", "multi_pv"),)
    position_id: Mapped[UUID] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"), index=True
    )
    analysis_type: Mapped[AnalysisType] = mapped_column(enum_type(AnalysisType, "analysis_type"))
    evaluation_cp: Mapped[int | None] = mapped_column(Integer)
    mate_score: Mapped[int | None] = mapped_column(Integer)
    best_move: Mapped[str | None] = mapped_column(String(5))
    principal_variation: Mapped[str | None] = mapped_column(Text())
    depth: Mapped[int | None] = mapped_column(Integer)
    nodes: Mapped[int | None] = mapped_column()
    time_ms: Mapped[int | None] = mapped_column(Integer)
    multi_pv: Mapped[int] = mapped_column(Integer, default=1)
    engine_name: Mapped[str | None] = mapped_column(String(100))
    engine_version: Mapped[str | None] = mapped_column(String(100))


class AnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (CheckConstraint("attempts >= 0", name="attempts_non_negative"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[UUID | None] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"))
    job_type: Mapped[AnalysisJobType] = mapped_column(
        enum_type(AnalysisJobType, "analysis_job_type")
    )
    status: Mapped[AnalysisJobStatus] = mapped_column(
        enum_type(AnalysisJobStatus, "analysis_job_status"), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "model_versions"
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    artifact_uri: Mapped[str] = mapped_column(String(1024))
    checksum: Mapped[str] = mapped_column(String(128))
    framework: Mapped[str] = mapped_column(String(100))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)


class EngineVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "engine_versions"
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    binary_checksum: Mapped[str] = mapped_column(String(128))
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
