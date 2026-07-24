"""Authorized post-game delivery and explicit internal-to-public mapping."""

from uuid import UUID

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.game_metrics import PlayerAnalyticalSummary
from boardtrace_api.analysis.move_classification import MoveQuality
from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus
from boardtrace_api.schemas.analysis_results import (
    PublicGameAnalysisResponse,
    PublicMoveAnalysis,
    PublicMoveColor,
    PublicMoveQuality,
    PublicMoveQualityCount,
    PublicPlayerAnalysis,
)
from boardtrace_api.services.analysis_aggregates import UnifiedInternalAnalysisAggregate
from boardtrace_api.services.analysis_facade import (
    InternalAnalysisReadFacade,
    compose_internal_analysis_read_facade,
)
from boardtrace_api.services.analysis_reads import InternalAnalysisReadError


class PublicAnalysisReadError(RuntimeError):
    """Public delivery error carrying no internal analysis data."""


class PublicAnalysisNotFoundError(PublicAnalysisReadError):
    pass


class PublicAnalysisUnavailableError(PublicAnalysisReadError):
    pass


class PublicAnalysisReadService:
    """Fail-closed public release gate over the canonical internal facade."""

    def __init__(
        self,
        session: AsyncSession,
        facade: InternalAnalysisReadFacade,
    ) -> None:
        self._session = session
        self._facade = facade

    async def read_for_owner(
        self,
        game_id: UUID,
        requesting_user_id: UUID,
    ) -> PublicGameAnalysisResponse:
        released = await self._session.scalar(
            select(Game.id).where(
                Game.id == game_id,
                Game.user_id == requesting_user_id,
                Game.status == GameStatus.ANALYSIS_AVAILABLE,
                Game.completion_verified_at.is_not(None),
            )
        )
        if released is None:
            raise PublicAnalysisNotFoundError("released analysis was not found")
        try:
            aggregate = await self._facade.read_for_owner(game_id, requesting_user_id)
        except InternalAnalysisReadError as error:
            raise PublicAnalysisUnavailableError("released analysis is unavailable") from error
        return map_public_analysis(aggregate)


def compose_public_analysis_read_service(session: AsyncSession) -> PublicAnalysisReadService:
    return PublicAnalysisReadService(
        session,
        compose_internal_analysis_read_facade(session),
    )


def map_public_analysis(
    aggregate: UnifiedInternalAnalysisAggregate,
) -> PublicGameAnalysisResponse:
    moves = tuple(
        PublicMoveAnalysis(
            ply=classified.metric.ply,
            move_uci=classified.metric.move_uci,
            move_san=classified.metric.move_san,
            mover=_color(classified.metric.mover),
            quality=PublicMoveQuality(classified.quality.value),
            centipawn_loss=classified.metric.centipawn_loss,
        )
        for classified in aggregate.classifications.moves
    )
    return PublicGameAnalysisResponse(
        game_id=aggregate.game_id,
        moves=moves,
        white=_player(aggregate.game_metrics.white),
        black=_player(aggregate.game_metrics.black),
    )


def _player(summary: PlayerAnalyticalSummary) -> PublicPlayerAnalysis:
    return PublicPlayerAnalysis(
        color=_color(summary.color),
        total_move_count=summary.total_move_count,
        cpl_eligible_move_count=summary.cpl_eligible_move_count,
        excluded_move_count=summary.excluded_move_count,
        cpl_coverage=summary.cpl_coverage,
        acpl=summary.acpl,
        accuracy=summary.accuracy,
        classified_move_count=summary.classified_move_count,
        unclassified_move_count=summary.unclassified_move_count,
        classification_coverage=summary.classification_coverage_percent,
        quality_counts=tuple(
            PublicMoveQualityCount(
                quality=_quality(item.quality),
                count=item.count,
            )
            for item in summary.quality_counts
        ),
    )


def _color(color: chess.Color) -> PublicMoveColor:
    return PublicMoveColor.WHITE if color == chess.WHITE else PublicMoveColor.BLACK


def _quality(quality: MoveQuality) -> PublicMoveQuality:
    return PublicMoveQuality(quality.value)
