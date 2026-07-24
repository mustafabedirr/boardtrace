"""Single internal provider boundary for authorized complete analysis reads."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.services.analysis_aggregates import (
    InternalAnalysisAggregateService,
    UnifiedInternalAnalysisAggregate,
)


class InternalAnalysisAggregateReader(Protocol):
    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> UnifiedInternalAnalysisAggregate: ...


class InternalAnalysisReadFacade:
    """The application-facing entry point for the complete Prompt 10 read chain."""

    def __init__(self, aggregate_service: InternalAnalysisAggregateReader) -> None:
        self._aggregate_service = aggregate_service

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> UnifiedInternalAnalysisAggregate:
        return await self._aggregate_service.read_for_owner(game_id, requesting_user_id)


def compose_internal_analysis_read_facade(
    session: AsyncSession,
) -> InternalAnalysisReadFacade:
    """Resolve the exact internal chain without registering a public dependency."""
    return InternalAnalysisReadFacade(InternalAnalysisAggregateService(session))
