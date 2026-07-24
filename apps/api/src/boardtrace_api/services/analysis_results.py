"""Transactional service boundary for internal full-game result persistence."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.full_game import (
    AnalysisCheckpoint,
    EngineReusePolicy,
    FullGameAnalysisResult,
    FullGameAnalysisStatus,
)
from boardtrace_api.analysis.stockfish import StockfishScore
from boardtrace_api.db.transactions import (
    BeforeCommitHook,
    TransactionBoundary,
    no_op_before_commit,
)
from boardtrace_api.models import AnalysisRun
from boardtrace_api.models.enums import AnalysisRunStatus
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.repositories.analysis_results import (
    AnalysisResultNotCompleteError,
    AnalysisResultRepository,
    AnalysisRunAuthorityError,
)


class PersistedAnalysisReadError(RuntimeError):
    """Raised when durable records violate the typed complete-run contract."""


@dataclass(frozen=True)
class PersistedPositionEvaluation:
    position_id: UUID
    ply: int
    side_to_move: chess.Color
    score: StockfishScore
    best_move_uci: str
    principal_variation_uci: tuple[str, ...]
    depth: int | None
    nodes: int | None
    time_ms: int | None


@dataclass(frozen=True)
class PersistedMoveEvaluation:
    ply: int
    move_uci: str
    move_san: str
    before: PersistedPositionEvaluation
    after: PersistedPositionEvaluation


@dataclass(frozen=True)
class PersistedCompleteAnalysisResult:
    game_id: UUID
    status: FullGameAnalysisStatus
    position_evaluations: tuple[PersistedPositionEvaluation, ...]
    move_evaluations: tuple[PersistedMoveEvaluation, ...]
    checkpoint: AnalysisCheckpoint
    engine_name: str | None
    engine_version: str | None
    engine_reuse_policy: EngineReusePolicy


@dataclass(frozen=True)
class EngineConfigurationSnapshot:
    schema_version: int
    depth: int
    max_position_time_ms: int
    max_game_time_ms: int
    max_positions: int
    max_moves: int
    threads: int
    hash_mb: int
    command_timeout_ms: int
    reuse_policy: EngineReusePolicy

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported engine configuration snapshot version")
        if not 1 <= self.depth <= 99:
            raise ValueError("snapshot depth is out of bounds")
        if not 1 <= self.max_position_time_ms <= 300_000:
            raise ValueError("snapshot position time is out of bounds")
        if not 1 <= self.max_game_time_ms <= 7_200_000:
            raise ValueError("snapshot game time is out of bounds")
        if not 2 <= self.max_positions <= 601:
            raise ValueError("snapshot position count is out of bounds")
        if not 1 <= self.max_moves <= 600:
            raise ValueError("snapshot move count is out of bounds")
        if not 1 <= self.threads <= 128:
            raise ValueError("snapshot thread count is out of bounds")
        if not 1 <= self.hash_mb <= 65_536:
            raise ValueError("snapshot hash size is out of bounds")
        if not 1 <= self.command_timeout_ms <= 300_000:
            raise ValueError("snapshot command timeout is out of bounds")

    def as_json(self) -> dict[str, object]:
        values = asdict(self)
        values["reuse_policy"] = self.reuse_policy.value
        return values

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "EngineConfigurationSnapshot":
        expected = {
            "schema_version",
            "depth",
            "max_position_time_ms",
            "max_game_time_ms",
            "max_positions",
            "max_moves",
            "threads",
            "hash_mb",
            "command_timeout_ms",
            "reuse_policy",
        }
        if set(value) != expected:
            raise PersistedAnalysisReadError("engine snapshot fields do not match schema")
        policy = value["reuse_policy"]
        if not isinstance(policy, str):
            raise PersistedAnalysisReadError("engine snapshot reuse policy is invalid")
        try:
            reuse_policy = EngineReusePolicy(policy)
            return cls(
                schema_version=_snapshot_int(value, "schema_version"),
                depth=_snapshot_int(value, "depth"),
                max_position_time_ms=_snapshot_int(value, "max_position_time_ms"),
                max_game_time_ms=_snapshot_int(value, "max_game_time_ms"),
                max_positions=_snapshot_int(value, "max_positions"),
                max_moves=_snapshot_int(value, "max_moves"),
                threads=_snapshot_int(value, "threads"),
                hash_mb=_snapshot_int(value, "hash_mb"),
                command_timeout_ms=_snapshot_int(value, "command_timeout_ms"),
                reuse_policy=reuse_policy,
            )
        except ValueError as error:
            raise PersistedAnalysisReadError("engine snapshot values are invalid") from error


@dataclass(frozen=True)
class PersistedFullGameAnalysis:
    run_id: UUID
    analysis_job_id: UUID
    lease_generation: int
    analysis_version: int
    result: PersistedCompleteAnalysisResult
    configuration: EngineConfigurationSnapshot
    started_at: datetime
    finished_at: datetime


class AnalysisResultPersistenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = AnalysisResultRepository(session)

    async def persist_owned_generation(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_generation: int,
        result: FullGameAnalysisResult,
        configuration: EngineConfigurationSnapshot,
        started_at: datetime,
        finished_at: datetime,
        before_commit: BeforeCommitHook = no_op_before_commit,
    ) -> AnalysisRun:
        if result.status is not FullGameAnalysisStatus.COMPLETE or result.failure is not None:
            raise AnalysisResultNotCompleteError("only complete analysis results may be persisted")
        if lease_generation < 1:
            raise ValueError("lease generation must be positive")
        if finished_at < started_at:
            raise ValueError("analysis finish time cannot precede start time")
        return await TransactionBoundary(self._session, before_commit).execute(
            lambda: self._repository.replace_owned_generation(
                job_id=job_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                result=result,
                configuration_snapshot=configuration.as_json(),
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    async def persist_and_complete_owned_generation(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_generation: int,
        result: FullGameAnalysisResult,
        configuration: EngineConfigurationSnapshot,
        started_at: datetime,
        finished_at: datetime,
        before_commit: BeforeCommitHook = no_op_before_commit,
    ) -> AnalysisRun:
        """Atomically persist a complete result and complete its authoritative job."""
        if result.status is not FullGameAnalysisStatus.COMPLETE or result.failure is not None:
            raise AnalysisResultNotCompleteError("only complete analysis results may be persisted")
        if lease_generation < 1:
            raise ValueError("lease generation must be positive")
        if finished_at < started_at:
            raise ValueError("analysis finish time cannot precede start time")

        async def persist_and_complete() -> AnalysisRun:
            run = await self._repository.replace_owned_generation(
                job_id=job_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                result=result,
                configuration_snapshot=configuration.as_json(),
                started_at=started_at,
                finished_at=finished_at,
            )
            completed = await AnalysisJobRepository(self._session).complete_job(
                job_id, worker_id, finished_at, lease_generation
            )
            if not completed:
                raise AnalysisRunAuthorityError("job completion authority was lost")
            return run

        return await TransactionBoundary(self._session, before_commit).execute(persist_and_complete)

    async def read_generation(
        self, job_id: UUID, lease_generation: int
    ) -> PersistedFullGameAnalysis | None:
        records = await self._repository.get_generation_records(job_id, lease_generation)
        if records is None:
            return None
        run, position_rows, move_rows = records
        if (
            run.status is not AnalysisRunStatus.COMPLETE
            or run.failure_code is not None
            or run.failure_error_type is not None
        ):
            raise PersistedAnalysisReadError("durable run is not complete-only")
        positions_by_record_id: dict[UUID, PersistedPositionEvaluation] = {}
        positions: list[PersistedPositionEvaluation] = []
        for position_row in position_rows:
            if position_row.side_to_move not in {"w", "b"}:
                raise PersistedAnalysisReadError("position side-to-move value is invalid")
            evaluation = PersistedPositionEvaluation(
                position_id=position_row.source_position_id,
                ply=position_row.ply,
                side_to_move=chess.WHITE if position_row.side_to_move == "w" else chess.BLACK,
                score=StockfishScore(
                    centipawns=position_row.centipawns, mate_in=position_row.mate_in
                ),
                best_move_uci=position_row.best_move_uci,
                principal_variation_uci=tuple(position_row.principal_variation_uci),
                depth=position_row.depth,
                nodes=position_row.nodes,
                time_ms=position_row.time_ms,
            )
            positions_by_record_id[position_row.id] = evaluation
            positions.append(evaluation)
        moves: list[PersistedMoveEvaluation] = []
        try:
            for move_row in move_rows:
                moves.append(
                    PersistedMoveEvaluation(
                        ply=move_row.ply,
                        move_uci=move_row.move_uci,
                        move_san=move_row.move_san,
                        before=positions_by_record_id[move_row.before_position_evaluation_id],
                        after=positions_by_record_id[move_row.after_position_evaluation_id],
                    )
                )
        except KeyError as error:
            raise PersistedAnalysisReadError("move references a missing position") from error
        if len(positions) != run.evaluated_positions or len(moves) != run.completed_moves:
            raise PersistedAnalysisReadError("durable record counts do not match run metadata")
        configuration = EngineConfigurationSnapshot.from_json(run.configuration_snapshot)
        result = PersistedCompleteAnalysisResult(
            game_id=run.game_id,
            status=FullGameAnalysisStatus.COMPLETE,
            position_evaluations=tuple(positions),
            move_evaluations=tuple(moves),
            checkpoint=AnalysisCheckpoint(
                total_moves=run.total_moves,
                total_positions=run.total_positions,
                completed_moves=run.completed_moves,
                evaluated_positions=run.evaluated_positions,
                last_evaluated_ply=positions[-1].ply if positions else None,
            ),
            engine_name=run.engine_name,
            engine_version=run.engine_version,
            engine_reuse_policy=configuration.reuse_policy,
        )
        return PersistedFullGameAnalysis(
            run_id=run.id,
            analysis_job_id=run.analysis_job_id,
            lease_generation=run.lease_generation,
            analysis_version=run.analysis_version,
            result=result,
            configuration=configuration,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )


def _snapshot_int(value: Mapping[str, object], field: str) -> int:
    item = value[field]
    if not isinstance(item, int) or isinstance(item, bool):
        raise PersistedAnalysisReadError(f"engine snapshot {field} is not an integer")
    return item
