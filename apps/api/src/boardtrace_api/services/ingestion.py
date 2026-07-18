from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus
from boardtrace_api.schemas.ingestion import CompletedGameIngestionRequest


class IngestionConflictError(Exception):
    pass


class CompletedGameIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def payload_hash(payload: CompletedGameIngestionRequest) -> str:
        canonical = dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    async def ingest(self, user_id: UUID, payload: CompletedGameIngestionRequest) -> Game:
        payload_hash = self.payload_hash(payload)
        existing = await self._session.scalar(
            select(Game).where(Game.ingestion_key == payload.idempotency_key)
        )
        if existing is not None:
            if existing.user_id != user_id or existing.ingestion_payload_hash != payload_hash:
                raise IngestionConflictError
            return existing

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
            ingestion_payload_hash=payload_hash,
        )
        self._session.add(game)
        await self._session.flush()
        return game

    async def get_for_user(self, game_id: UUID, user_id: UUID) -> Game | None:
        return cast(
            Game | None,
            await self._session.scalar(
                select(Game).where(Game.id == game_id, Game.user_id == user_id)
            ),
        )
