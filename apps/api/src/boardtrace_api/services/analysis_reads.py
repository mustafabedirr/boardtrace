"""Authorized, non-public application read boundary for complete analysis snapshots."""

from dataclasses import dataclass
from uuid import UUID

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models.enums import GameStatus
from boardtrace_api.repositories.analysis_reads import AnalysisReadRepository
from boardtrace_api.services.analysis_results import (
    AnalysisResultPersistenceService,
    PersistedAnalysisReadError,
    PersistedFullGameAnalysis,
)


class InternalAnalysisReadError(RuntimeError):
    """Base error carrying no engine output or durable payload."""


class AnalysisGameNotFoundError(InternalAnalysisReadError):
    pass


class AnalysisReadForbiddenError(InternalAnalysisReadError):
    pass


class AnalysisSnapshotUnavailableError(InternalAnalysisReadError):
    pass


class AnalysisSnapshotCorruptError(InternalAnalysisReadError):
    pass


@dataclass(frozen=True)
class InternalAnalysisSnapshot:
    game_id: UUID
    owner_user_id: UUID
    analysis: PersistedFullGameAnalysis


class InternalAnalysisReadService:
    """Never exposed as a FastAPI dependency or public response serializer."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = AnalysisReadRepository(session)
        self._result_reader = AnalysisResultPersistenceService(session)

    async def read_for_owner(
        self, game_id: UUID, requesting_user_id: UUID
    ) -> InternalAnalysisSnapshot:
        authority = await self._repository.get_game_authority(game_id)
        if authority is None:
            raise AnalysisGameNotFoundError("analysis game was not found")
        if authority.owner_user_id != requesting_user_id:
            raise AnalysisReadForbiddenError("analysis snapshot access is forbidden")
        if (
            authority.status
            not in {
                GameStatus.FINISHED,
                GameStatus.DEEP_ANALYSIS_RUNNING,
                GameStatus.ANALYSIS_AVAILABLE,
            }
            or not authority.completion_verified
        ):
            raise AnalysisSnapshotUnavailableError("analysis snapshot is unavailable")

        reference = await self._repository.get_current_authoritative_run(game_id)
        if reference is None:
            raise AnalysisSnapshotUnavailableError("analysis snapshot is unavailable")
        if reference.run_id is None:
            raise AnalysisSnapshotCorruptError("authoritative analysis run is missing")
        try:
            analysis = await self._result_reader.read_generation(
                reference.job_id, reference.lease_generation
            )
        except (PersistedAnalysisReadError, ValueError) as error:
            raise AnalysisSnapshotCorruptError("analysis snapshot failed validation") from error
        if analysis is None:
            raise AnalysisSnapshotCorruptError("authoritative analysis run is missing")
        if (
            analysis.run_id != reference.run_id
            or analysis.analysis_version != reference.analysis_version
            or analysis.result.game_id != game_id
        ):
            raise AnalysisSnapshotCorruptError("analysis snapshot authority does not match")
        _validate_complete_snapshot(analysis)
        return InternalAnalysisSnapshot(game_id, requesting_user_id, analysis)


def _validate_complete_snapshot(analysis: PersistedFullGameAnalysis) -> None:
    result = analysis.result
    positions = result.position_evaluations
    moves = result.move_evaluations
    checkpoint = result.checkpoint
    if tuple(position.ply for position in positions) != tuple(range(len(positions))):
        raise AnalysisSnapshotCorruptError("analysis positions are not contiguous")
    if tuple(move.ply for move in moves) != tuple(range(1, len(moves) + 1)):
        raise AnalysisSnapshotCorruptError("analysis moves are not contiguous")
    if (
        checkpoint.total_positions != len(positions)
        or checkpoint.evaluated_positions != len(positions)
        or checkpoint.total_moves != len(moves)
        or checkpoint.completed_moves != len(moves)
    ):
        raise AnalysisSnapshotCorruptError("analysis checkpoint does not match records")
    for move in moves:
        if move.before.ply != move.ply - 1 or move.after.ply != move.ply:
            raise AnalysisSnapshotCorruptError("analysis move references are invalid")
        _require_uci(move.move_uci)
    for position in positions:
        _require_uci(position.best_move_uci)
        for principal_variation_move in position.principal_variation_uci:
            _require_uci(principal_variation_move)
        if position.depth is not None and position.depth < 1:
            raise AnalysisSnapshotCorruptError("analysis depth is invalid")
        if position.nodes is not None and position.nodes < 0:
            raise AnalysisSnapshotCorruptError("analysis node count is invalid")
        if position.time_ms is not None and position.time_ms < 0:
            raise AnalysisSnapshotCorruptError("analysis time is invalid")


def _require_uci(value: str) -> None:
    try:
        chess.Move.from_uci(value)
    except ValueError as error:
        raise AnalysisSnapshotCorruptError("analysis move encoding is invalid") from error
