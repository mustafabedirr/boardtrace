"""Internal-only authority lookup for persisted analysis snapshots."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AnalysisJob, AnalysisRun, Game
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisRunStatus, GameStatus


@dataclass(frozen=True)
class GameReadAuthority:
    game_id: UUID
    owner_user_id: UUID
    status: GameStatus
    completion_verified: bool


@dataclass(frozen=True)
class AuthoritativeRunReference:
    job_id: UUID
    run_id: UUID | None
    lease_generation: int
    analysis_version: int


class AnalysisReadRepository:
    """Performs authorization lookup before any engine-result table query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_game_authority(self, game_id: UUID) -> GameReadAuthority | None:
        row = (
            await self._session.execute(
                select(
                    Game.id,
                    Game.user_id,
                    Game.status,
                    Game.completion_verified_at,
                ).where(Game.id == game_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return GameReadAuthority(
            game_id=row.id,
            owner_user_id=row.user_id,
            status=row.status,
            completion_verified=row.completion_verified_at is not None,
        )

    async def get_current_authoritative_run(
        self, game_id: UUID
    ) -> AuthoritativeRunReference | None:
        current_job = await self._session.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.game_id == game_id)
            .order_by(
                AnalysisJob.analysis_version.desc(),
                AnalysisJob.created_at.desc(),
                AnalysisJob.id.desc(),
            )
            .limit(1)
        )
        if current_job is None or current_job.status is not AnalysisJobStatus.SUCCEEDED:
            return None
        run = await self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.analysis_job_id == current_job.id,
                AnalysisRun.game_id == game_id,
                AnalysisRun.lease_generation == current_job.lease_generation,
                AnalysisRun.analysis_version == current_job.analysis_version,
                AnalysisRun.status == AnalysisRunStatus.COMPLETE,
            )
        )
        if run is None:
            return AuthoritativeRunReference(
                job_id=current_job.id,
                run_id=None,
                lease_generation=current_job.lease_generation,
                analysis_version=current_job.analysis_version,
            )
        return AuthoritativeRunReference(
            job_id=current_job.id,
            run_id=run.id,
            lease_generation=run.lease_generation,
            analysis_version=run.analysis_version,
        )
