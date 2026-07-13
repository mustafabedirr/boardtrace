from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import Game


class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, game_id: UUID) -> Game | None:
        return await self._session.get(Game, game_id)

    def add(self, game: Game) -> None:
        self._session.add(game)

    async def get_for_user(self, user_id: UUID) -> list[Game]:
        result = await self._session.scalars(select(Game).where(Game.user_id == user_id))
        return list(result)
