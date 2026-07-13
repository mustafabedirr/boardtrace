from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import EngineAnalysis


class EngineAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, analysis: EngineAnalysis) -> None:
        self._session.add(analysis)

    async def get_for_position(self, position_id: UUID) -> list[EngineAnalysis]:
        result = await self._session.scalars(
            select(EngineAnalysis).where(EngineAnalysis.position_id == position_id)
        )
        return list(result)
