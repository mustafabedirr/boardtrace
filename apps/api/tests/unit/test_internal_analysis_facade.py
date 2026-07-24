from uuid import UUID, uuid4

import pytest

from boardtrace_api.services.analysis_aggregates import UnifiedInternalAnalysisAggregate
from boardtrace_api.services.analysis_facade import InternalAnalysisReadFacade


class AggregateServiceSpy:
    def __init__(self, result: UnifiedInternalAnalysisAggregate) -> None:
        self.result = result
        self.calls: list[tuple[UUID, UUID]] = []

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> UnifiedInternalAnalysisAggregate:
        self.calls.append((game_id, requesting_user_id))
        return self.result


@pytest.mark.asyncio
async def test_facade_delegates_once_and_preserves_aggregate_identity() -> None:
    result = object.__new__(UnifiedInternalAnalysisAggregate)
    service = AggregateServiceSpy(result)
    facade = InternalAnalysisReadFacade(service)
    game_id = uuid4()
    owner_id = uuid4()

    resolved = await facade.read_for_owner(game_id, owner_id)

    assert resolved is result
    assert service.calls == [(game_id, owner_id)]
