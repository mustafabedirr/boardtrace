from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import Position


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, position_id: UUID) -> Position | None:
        return await self._session.get(Position, position_id)

    def add(self, position: Position) -> None:
        self._session.add(position)

    async def get_for_game(self, game_id: UUID) -> list[Position]:
        result = await self._session.scalars(
            select(Position).where(Position.game_id == game_id).order_by(Position.ply)
        )
        return list(result)
