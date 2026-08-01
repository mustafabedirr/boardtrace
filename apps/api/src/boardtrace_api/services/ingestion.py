from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus
from boardtrace_api.provenance import validate_source
from boardtrace_api.schemas.ingestion import CompletedGameIngestionRequest
from boardtrace_api.services.analysis_jobs import AnalysisJobService


class IngestionConflictError(Exception):
    pass


class CompletedGameIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        require_source_checksum: bool = False,
        enqueue_analysis: bool = True,
    ) -> None:
        self._session = session
        self._require_source_checksum = require_source_checksum
        self._enqueue_analysis = enqueue_analysis

    async def ingest(self, user_id: UUID, payload: CompletedGameIngestionRequest) -> Game:
        source_checksum = validate_source(
            platform=payload.platform,
            source_game_id=payload.source_game_id,
            acquisition_method=payload.acquisition_method,
            moves=payload.moves,
            supplied_checksum=payload.source_checksum,
            require_checksum=self._require_source_checksum,
        )
        existing = await self._session.scalar(
            select(Game).where(Game.ingestion_key == payload.idempotency_key)
        )
        if existing is not None:
            if existing.user_id != user_id or existing.ingestion_payload_hash != source_checksum:
                raise IngestionConflictError
            if existing.status is not GameStatus.ANALYSIS_AVAILABLE:
                await AnalysisJobService(self._session).create_for_completed_game(
                    existing.id, uuid4(), enqueue=self._enqueue_analysis
                )
            return existing

        try:
            async with self._session.begin_nested():
                game = Game(
                    user_id=user_id,
                    status=GameStatus.FINISHED,
                    platform=payload.platform,
                    source_game_id=payload.source_game_id,
                    player_color=payload.player_color,
                    result=payload.result,
                    started_at=None,
                    finished_at=payload.completed_at,
                    completion_verified_at=datetime.now(UTC),
                    initial_fen=payload.initial_fen,
                    normalized_moves=payload.moves,
                    ingestion_key=payload.idempotency_key,
                    ingestion_payload_hash=source_checksum,
                )
                self._session.add(game)
                await self._session.flush()
        except IntegrityError:
            existing = cast(
                Game | None,
                await self._session.scalar(
                    select(Game).where(Game.ingestion_key == payload.idempotency_key)
                ),
            )
            if (
                existing is None
                or existing.user_id != user_id
                or existing.ingestion_payload_hash != source_checksum
            ):
                raise IngestionConflictError from None
            if existing.status is not GameStatus.ANALYSIS_AVAILABLE:
                await AnalysisJobService(self._session).create_for_completed_game(
                    existing.id, uuid4(), enqueue=self._enqueue_analysis
                )
            return existing

        await AnalysisJobService(self._session).create_for_completed_game(
            game.id, uuid4(), enqueue=self._enqueue_analysis
        )
        return game

    async def get_for_user(self, game_id: UUID, user_id: UUID) -> Game | None:
        return cast(
            Game | None,
            await self._session.scalar(
                select(Game).where(Game.id == game_id, Game.user_id == user_id)
            ),
        )
