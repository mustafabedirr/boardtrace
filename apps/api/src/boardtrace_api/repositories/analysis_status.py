"""Read-only current-authority projection for public readiness mapping."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AnalysisJob, AnalysisRun, Game
from boardtrace_api.models.enums import AnalysisJobStatus, AnalysisRunStatus, GameStatus


@dataclass(frozen=True)
class PublicReadinessAuthority:
    game_id: UUID
    game_status: GameStatus
    job_status: AnalysisJobStatus | None
    has_current_complete_run: bool


class AnalysisStatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owner_readiness_authority(
        self,
        game_id: UUID,
        owner_user_id: UUID,
    ) -> PublicReadinessAuthority | None:
        game = await self._session.execute(
            select(Game.id, Game.status).where(
                Game.id == game_id,
                Game.user_id == owner_user_id,
                Game.completion_verified_at.is_not(None),
                Game.status.in_(
                    {
                        GameStatus.FINISHED,
                        GameStatus.DEEP_ANALYSIS_RUNNING,
                        GameStatus.ANALYSIS_AVAILABLE,
                        GameStatus.FAILED,
                    }
                ),
            )
        )
        game_row = game.one_or_none()
        if game_row is None:
            return None
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
        if current_job is None:
            return PublicReadinessAuthority(
                game_id=game_row.id,
                game_status=game_row.status,
                job_status=None,
                has_current_complete_run=False,
            )
        has_complete_run = False
        if current_job.status is AnalysisJobStatus.SUCCEEDED:
            run_id = await self._session.scalar(
                select(AnalysisRun.id).where(
                    AnalysisRun.analysis_job_id == current_job.id,
                    AnalysisRun.game_id == game_id,
                    AnalysisRun.lease_generation == current_job.lease_generation,
                    AnalysisRun.analysis_version == current_job.analysis_version,
                    AnalysisRun.status == AnalysisRunStatus.COMPLETE,
                )
            )
            has_complete_run = run_id is not None
        return PublicReadinessAuthority(
            game_id=game_row.id,
            game_status=game_row.status,
            job_status=current_job.status,
            has_current_complete_run=has_complete_run,
        )
