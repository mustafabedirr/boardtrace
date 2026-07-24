"""Generation-authorized persistence for internal full-game analysis records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.full_game import FullGameAnalysisResult, FullGameAnalysisStatus
from boardtrace_api.models import (
    AnalysisJob,
    AnalysisMoveEvaluation,
    AnalysisPositionEvaluation,
    AnalysisRun,
    Game,
)
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisRunStatus, GameStatus

RUN_ID_NAMESPACE = UUID("ae3e4f24-18f4-49ea-9237-49b8ac09e5d7")
POSITION_RECORD_ID_NAMESPACE = UUID("34dc814b-b29e-4d21-9462-4c27d84fa95f")
MOVE_RECORD_ID_NAMESPACE = UUID("8daf3171-2798-4489-9be4-78641c68e512")


class AnalysisRunAuthorityError(PermissionError):
    """Raised when a worker no longer owns the exact job generation."""


class AnalysisResultContractError(ValueError):
    """Raised before writes when an in-memory result is internally inconsistent."""


class AnalysisResultNotCompleteError(AnalysisResultContractError):
    """Raised when non-complete orchestration output reaches persistence."""


class AnalysisResultRepository:
    """Stages an all-or-nothing generation replacement; never commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_owned_generation(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_generation: int,
        result: FullGameAnalysisResult,
        configuration_snapshot: Mapping[str, object],
        started_at: datetime,
        finished_at: datetime,
    ) -> AnalysisRun:
        _require_complete_result(result)
        job = await self._session.scalar(
            select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
        )
        game = (
            await self._session.scalar(select(Game).where(Game.id == job.game_id).with_for_update())
            if job is not None
            else None
        )
        if (
            job is None
            or game is None
            or job.status != AnalysisJobStatus.RUNNING
            or job.worker_id != worker_id
            or job.lease_generation != lease_generation
            or job.game_id != result.game_id
            or game.status not in {GameStatus.FINISHED, GameStatus.DEEP_ANALYSIS_RUNNING}
            or game.completion_verified_at is None
        ):
            raise AnalysisRunAuthorityError("worker does not own this analysis generation")

        _validate_result(result)
        run_id = analysis_run_id(job_id, lease_generation)
        run = await self._session.get(AnalysisRun, run_id)
        if run is None:
            run = AnalysisRun(
                id=run_id,
                analysis_job_id=job.id,
                game_id=job.game_id,
                lease_generation=lease_generation,
                analysis_version=job.analysis_version,
                status=_run_status(result.status),
                engine_name=_bounded(result.engine_name, 100),
                engine_version=_bounded(result.engine_version, 100),
                configuration_snapshot=dict(configuration_snapshot),
                total_positions=result.checkpoint.total_positions,
                evaluated_positions=result.checkpoint.evaluated_positions,
                total_moves=result.checkpoint.total_moves,
                completed_moves=result.checkpoint.completed_moves,
                failure_code=_failure_code(result),
                failure_error_type=_failure_error_type(result),
                started_at=started_at,
                finished_at=finished_at,
            )
            self._session.add(run)
            await self._session.flush()
        else:
            await self._session.execute(
                delete(AnalysisMoveEvaluation).where(
                    AnalysisMoveEvaluation.analysis_run_id == run_id
                )
            )
            await self._session.execute(
                delete(AnalysisPositionEvaluation).where(
                    AnalysisPositionEvaluation.analysis_run_id == run_id
                )
            )
            run.status = _run_status(result.status)
            run.engine_name = _bounded(result.engine_name, 100)
            run.engine_version = _bounded(result.engine_version, 100)
            run.configuration_snapshot = dict(configuration_snapshot)
            run.total_positions = result.checkpoint.total_positions
            run.evaluated_positions = result.checkpoint.evaluated_positions
            run.total_moves = result.checkpoint.total_moves
            run.completed_moves = result.checkpoint.completed_moves
            run.failure_code = _failure_code(result)
            run.failure_error_type = _failure_error_type(result)
            run.started_at = started_at
            run.finished_at = finished_at

        position_ids: dict[int, UUID] = {}
        for evaluation in sorted(result.position_evaluations, key=lambda item: item.ply):
            record_id = position_evaluation_id(run_id, evaluation.ply)
            position_ids[evaluation.ply] = record_id
            self._session.add(
                AnalysisPositionEvaluation(
                    id=record_id,
                    analysis_run_id=run_id,
                    source_position_id=evaluation.position_id,
                    ply=evaluation.ply,
                    side_to_move="w" if evaluation.side_to_move else "b",
                    centipawns=evaluation.score.centipawns,
                    mate_in=evaluation.score.mate_in,
                    best_move_uci=evaluation.best_move_uci,
                    principal_variation_uci=list(evaluation.principal_variation_uci),
                    depth=evaluation.depth,
                    nodes=evaluation.nodes,
                    time_ms=evaluation.time_ms,
                )
            )
        await self._session.flush()

        for move in sorted(result.move_evaluations, key=lambda item: item.ply):
            self._session.add(
                AnalysisMoveEvaluation(
                    id=move_evaluation_id(run_id, move.ply),
                    analysis_run_id=run_id,
                    ply=move.ply,
                    move_uci=move.move_uci,
                    move_san=move.move_san,
                    before_position_evaluation_id=position_ids[move.before.ply],
                    after_position_evaluation_id=position_ids[move.after.ply],
                )
            )
        await self._session.flush()
        return run

    async def get_generation_records(
        self, job_id: UUID, lease_generation: int
    ) -> (
        tuple[
            AnalysisRun,
            tuple[AnalysisPositionEvaluation, ...],
            tuple[AnalysisMoveEvaluation, ...],
        ]
        | None
    ):
        run = await self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.analysis_job_id == job_id,
                AnalysisRun.lease_generation == lease_generation,
            )
        )
        if run is None:
            return None
        positions = tuple(
            await self._session.scalars(
                select(AnalysisPositionEvaluation)
                .where(AnalysisPositionEvaluation.analysis_run_id == run.id)
                .order_by(AnalysisPositionEvaluation.ply)
            )
        )
        moves = tuple(
            await self._session.scalars(
                select(AnalysisMoveEvaluation)
                .where(AnalysisMoveEvaluation.analysis_run_id == run.id)
                .order_by(AnalysisMoveEvaluation.ply)
            )
        )
        return run, positions, moves


def analysis_run_id(job_id: UUID, lease_generation: int) -> UUID:
    return uuid5(RUN_ID_NAMESPACE, f"{job_id}:{lease_generation}")


def position_evaluation_id(run_id: UUID, ply: int) -> UUID:
    return uuid5(POSITION_RECORD_ID_NAMESPACE, f"{run_id}:{ply}")


def move_evaluation_id(run_id: UUID, ply: int) -> UUID:
    return uuid5(MOVE_RECORD_ID_NAMESPACE, f"{run_id}:{ply}")


def _validate_result(result: FullGameAnalysisResult) -> None:
    _require_complete_result(result)
    positions = tuple(sorted(result.position_evaluations, key=lambda item: item.ply))
    moves = tuple(sorted(result.move_evaluations, key=lambda item: item.ply))
    if tuple(item.ply for item in positions) != tuple(range(len(positions))):
        raise AnalysisResultContractError("position evaluations must be contiguous from ply zero")
    if tuple(item.ply for item in moves) != tuple(range(1, len(moves) + 1)):
        raise AnalysisResultContractError("move evaluations must be contiguous from ply one")
    if result.checkpoint.evaluated_positions != len(positions):
        raise AnalysisResultContractError("position checkpoint does not match records")
    if result.checkpoint.completed_moves != len(moves):
        raise AnalysisResultContractError("move checkpoint does not match records")
    if result.failure is not None:
        raise AnalysisResultContractError("complete result cannot contain failure metadata")
    for move in moves:
        if move.before.ply != move.ply - 1 or move.after.ply != move.ply:
            raise AnalysisResultContractError("move position references do not match ordering")


def _run_status(status: FullGameAnalysisStatus) -> AnalysisRunStatus:
    if status is not FullGameAnalysisStatus.COMPLETE:
        raise AnalysisResultNotCompleteError("only complete analysis results may be persisted")
    return AnalysisRunStatus.COMPLETE


def _bounded(value: str | None, length: int) -> str | None:
    return value[:length] if value is not None else None


def _failure_code(result: FullGameAnalysisResult) -> str | None:
    return result.failure.code.value[:100] if result.failure is not None else None


def _failure_error_type(result: FullGameAnalysisResult) -> str | None:
    return result.failure.error_type[:100] if result.failure is not None else None


def _require_complete_result(result: FullGameAnalysisResult) -> None:
    if result.status is not FullGameAnalysisStatus.COMPLETE or result.failure is not None:
        raise AnalysisResultNotCompleteError("only complete analysis results may be persisted")
