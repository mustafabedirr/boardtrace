"""Authorized post-game delivery and explicit internal-to-public mapping."""

from uuid import UUID

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.analysis.game_metrics import PlayerAnalyticalSummary
from boardtrace_api.analysis.move_classification import MoveQuality
from boardtrace_api.analysis.observability import audit_event_safely
from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus
from boardtrace_api.repositories.analysis_results import AnalysisResultRepository
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
from boardtrace_api.services.analysis_results import PersistedMoveEvaluation


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
        response = map_public_analysis(aggregate)
        consumed = await AnalysisResultRepository(self._session).consume_public_generation(
            aggregate.snapshot.analysis.run_id,
            game_id,
        )
        if not consumed:
            await self._session.rollback()
            raise PublicAnalysisNotFoundError("released analysis was already consumed")
        await self._session.commit()
        audit_event_safely(
            "analysis_session_result_consumed",
            game_id=str(game_id),
            outcome="deleted_after_delivery",
        )
        return response


def compose_public_analysis_read_service(session: AsyncSession) -> PublicAnalysisReadService:
    return PublicAnalysisReadService(
        session,
        compose_internal_analysis_read_facade(session),
    )


def map_public_analysis(
    aggregate: UnifiedInternalAnalysisAggregate,
) -> PublicGameAnalysisResponse:
    persisted_moves_by_ply = _persisted_moves_by_ply(aggregate)
    board = chess.Board()
    public_moves: list[PublicMoveAnalysis] = []
    for classified in aggregate.classifications.moves:
        persisted = _linked_persisted_move(
            classified.metric.ply,
            classified.metric.move_uci,
            classified.metric.move_san,
            persisted_moves_by_ply,
        )
        if board.turn != classified.metric.mover:
            raise PublicAnalysisUnavailableError("released analysis mover linkage is invalid")
        played_move = _legal_move(board, classified.metric.move_uci)
        if board.san(played_move) != classified.metric.move_san:
            raise PublicAnalysisUnavailableError("released analysis SAN linkage is invalid")
        engine_move = _legal_move(board, persisted.before.best_move_uci)
        alternative_san = None if engine_move == played_move else board.san(engine_move)
        public_moves.append(
            PublicMoveAnalysis(
                ply=classified.metric.ply,
                move_uci=classified.metric.move_uci,
                move_san=classified.metric.move_san,
                mover=_color(classified.metric.mover),
                quality=PublicMoveQuality(classified.quality.value),
                centipawn_loss=classified.metric.centipawn_loss,
                alternative_san=alternative_san,
                after_position_centipawns=persisted.after.score.centipawns,
            )
        )
        board.push(played_move)
    return PublicGameAnalysisResponse(
        game_id=aggregate.game_id,
        moves=tuple(public_moves),
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


def _persisted_moves_by_ply(
    aggregate: UnifiedInternalAnalysisAggregate,
) -> dict[int, PersistedMoveEvaluation]:
    persisted_moves = aggregate.snapshot.analysis.result.move_evaluations
    by_ply = {move.ply: move for move in persisted_moves}
    if len(by_ply) != len(persisted_moves):
        raise PublicAnalysisUnavailableError("released analysis move linkage is invalid")
    return by_ply


def _linked_persisted_move(
    ply: int,
    move_uci: str,
    move_san: str,
    persisted_moves_by_ply: dict[int, PersistedMoveEvaluation],
) -> PersistedMoveEvaluation:
    persisted = persisted_moves_by_ply.get(ply)
    if (
        persisted is None
        or persisted.move_uci != move_uci
        or persisted.move_san != move_san
        or persisted.before.ply != ply - 1
        or persisted.after.ply != ply
    ):
        raise PublicAnalysisUnavailableError("released analysis move linkage is invalid")
    return persisted


def _legal_move(board: chess.Board, move_uci: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError as error:
        raise PublicAnalysisUnavailableError(
            "released analysis move encoding is invalid"
        ) from error
    if move not in board.legal_moves:
        raise PublicAnalysisUnavailableError("released analysis move legality is invalid")
    return move
