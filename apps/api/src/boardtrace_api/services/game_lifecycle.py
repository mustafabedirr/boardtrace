"""Read-only owner-scoped game lifecycle boundary."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus


@dataclass(frozen=True)
class OwnerGameLifecycle:
    game_id: UUID
    lifecycle: GameStatus
    completion_verified: bool


class OwnerGameLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> OwnerGameLifecycle | None:
        row = (
            await self._session.execute(
                select(
                    Game.id,
                    Game.status,
                    Game.completion_verified_at,
                ).where(
                    Game.id == game_id,
                    Game.user_id == requesting_user_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return OwnerGameLifecycle(
            game_id=row.id,
            lifecycle=row.status,
            completion_verified=row.completion_verified_at is not None,
        )
