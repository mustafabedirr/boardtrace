"""Idempotent terminal deletion of submitted game and provenance data."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.observability import audit_event_safely
from boardtrace_api.models import AnalysisJob, Game, GameFrame, Position


class GameDataCleanup(Protocol):
    async def delete_for_job(self, job_id: UUID) -> bool: ...


class TerminalGameDataCleanup:
    """Stages cleanup; the caller owns and commits the surrounding transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_for_job(self, job_id: UUID) -> bool:
        game_id = cast(
            UUID | None,
            await self._session.scalar(select(AnalysisJob.game_id).where(AnalysisJob.id == job_id)),
        )
        if game_id is None:
            return False
        game = await self._session.scalar(select(Game).where(Game.id == game_id).with_for_update())
        if game is None:
            return False
        await self._session.execute(delete(Position).where(Position.game_id == game_id))
        await self._session.execute(delete(GameFrame).where(GameFrame.game_id == game_id))
        game.platform = "deleted"
        game.source_game_id = None
        game.initial_fen = None
        game.normalized_moves = None
        game.ingestion_key = None
        game.ingestion_payload_hash = None
        return True


def record_cleanup(job_id: UUID, outcome: str) -> None:
    audit_event_safely(
        "analysis_terminal_game_data_cleanup",
        job_id=str(job_id),
        outcome=outcome,
    )
