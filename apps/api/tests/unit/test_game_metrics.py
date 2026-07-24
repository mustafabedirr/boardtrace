from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

import chess
import pytest

from boardtrace_api.analysis.game_metrics import (
    AccuracyPolicy,
    GameMetricAggregationService,
    InternalGameAnalyticalAggregate,
    PlayerAnalyticalSummary,
)
from boardtrace_api.analysis.move_classification import (
    ClassifiedMoveMetric,
    InternalClassifiedMoveMetrics,
    MoveClassificationService,
    MoveQuality,
)
from boardtrace_api.analysis.move_metrics import MoveMetricInput, derive_move_metric
from boardtrace_api.analysis.stockfish import StockfishScore


def _classified_move(
    *,
    ply: int,
    mover: chess.Color,
    before_cp: int | None = None,
    after_cp: int | None = None,
    before_mate: int | None = None,
    after_mate: int | None = None,
    reference: str | None = "d2d4",
) -> ClassifiedMoveMetric:
    before = (
        StockfishScore(centipawns=before_cp)
        if before_cp is not None
        else StockfishScore(mate_in=before_mate)
        if before_mate is not None
        else None
    )
    after = (
        StockfishScore(centipawns=-after_cp)
        if after_cp is not None
        else StockfishScore(mate_in=-after_mate)
        if after_mate is not None
        else None
    )
    played = "e2e4" if mover == chess.WHITE else "e7e5"
    return MoveClassificationService().classify_move(
        derive_move_metric(
            MoveMetricInput(
                ply=ply,
                move_uci=played,
                move_san="move",
                reference_best_move_uci=reference,
                mover=mover,
                before_side_to_move=mover,
                after_side_to_move=not mover,
                before_score=before,
                after_score=after,
                after_is_terminal=False,
            )
        )
    )


def _game_moves() -> tuple[ClassifiedMoveMetric, ...]:
    return (
        _classified_move(ply=1, mover=chess.WHITE, before_cp=100, after_cp=80),
        _classified_move(ply=2, mover=chess.BLACK, before_cp=100, after_cp=0),
        _classified_move(ply=3, mover=chess.WHITE, before_cp=50, after_cp=80),
        _classified_move(ply=4, mover=chess.BLACK, before_cp=None, after_cp=0),
        _classified_move(
            ply=5,
            mover=chess.WHITE,
            before_mate=3,
            after_mate=2,
            reference=None,
        ),
    )


def _classified_game(
    moves: tuple[ClassifiedMoveMetric, ...] | None = None,
) -> InternalClassifiedMoveMetrics:
    typed_moves = moves if moves is not None else _game_moves()
    return InternalClassifiedMoveMetrics(
        game_id=uuid4(),
        analysis_run_id=uuid4(),
        lease_generation=2,
        moves=typed_moves,
    )


def _counts(summary: PlayerAnalyticalSummary) -> dict[MoveQuality, int]:
    return {item.quality: item.count for item in summary.quality_counts}


def test_partitions_players_and_aggregates_cpl_accuracy_and_classification() -> None:
    aggregate = GameMetricAggregationService().aggregate(_classified_game())

    assert aggregate.white.total_move_count == 3
    assert aggregate.white.cpl_eligible_move_count == 2
    assert aggregate.white.excluded_move_count == 1
    assert aggregate.white.cpl_coverage == Decimal("66.67")
    assert aggregate.white.summed_centipawn_loss == 20
    assert aggregate.white.acpl == Decimal("10.00")
    assert aggregate.white.accuracy_available
    assert aggregate.white.accuracy == Decimal("90.91")
    assert aggregate.white.classified_move_count == 3
    assert aggregate.white.unclassified_move_count == 0
    assert aggregate.white.classification_coverage_percent == Decimal("100.00")
    assert _counts(aggregate.white)[MoveQuality.EXCELLENT] == 2
    assert _counts(aggregate.white)[MoveQuality.GOOD] == 1

    assert aggregate.black.total_move_count == 2
    assert aggregate.black.cpl_eligible_move_count == 1
    assert aggregate.black.excluded_move_count == 1
    assert aggregate.black.cpl_coverage == Decimal("50.00")
    assert aggregate.black.summed_centipawn_loss == 100
    assert aggregate.black.acpl == Decimal("100.00")
    assert aggregate.black.accuracy == Decimal("50.00")
    assert aggregate.black.classified_move_count == 1
    assert aggregate.black.unclassified_move_count == 1
    assert aggregate.black.classification_coverage_percent == Decimal("50.00")
    assert _counts(aggregate.black)[MoveQuality.INACCURACY] == 1
    assert _counts(aggregate.black)[MoveQuality.UNCLASSIFIED] == 1


def test_non_cpl_and_mate_moves_are_excluded_from_acpl_but_counted_in_labels() -> None:
    moves = (
        _classified_move(
            ply=1,
            mover=chess.WHITE,
            before_mate=3,
            after_mate=2,
            reference=None,
        ),
        _classified_move(ply=2, mover=chess.BLACK, before_cp=None, after_cp=0),
    )
    aggregate = GameMetricAggregationService().aggregate(_classified_game(moves))

    assert aggregate.white.cpl_eligible_move_count == 0
    assert aggregate.white.excluded_move_count == 1
    assert aggregate.white.cpl_coverage == Decimal("0.00")
    assert aggregate.white.acpl is None
    assert not aggregate.white.accuracy_available
    assert aggregate.white.accuracy is None
    assert _counts(aggregate.white)[MoveQuality.GOOD] == 1
    assert aggregate.black.acpl is None
    assert aggregate.black.accuracy is None
    assert aggregate.black.cpl_coverage == Decimal("0.00")
    assert _counts(aggregate.black)[MoveQuality.UNCLASSIFIED] == 1


def test_player_without_moves_has_unavailable_accuracy_and_coverage() -> None:
    moves = (_classified_move(ply=1, mover=chess.WHITE, before_cp=20, after_cp=20),)
    aggregate = GameMetricAggregationService().aggregate(_classified_game(moves))

    assert aggregate.black.total_move_count == 0
    assert aggregate.black.acpl is None
    assert not aggregate.black.accuracy_available
    assert aggregate.black.accuracy is None
    assert aggregate.black.cpl_coverage is None
    assert aggregate.black.classification_coverage_percent is None
    assert sum(_counts(aggregate.black).values()) == 0


@pytest.mark.parametrize(
    ("acpl", "accuracy"),
    [
        (Decimal("0"), Decimal("100.00")),
        (Decimal("10"), Decimal("90.91")),
        (Decimal("50"), Decimal("66.67")),
        (Decimal("100"), Decimal("50.00")),
        (Decimal("300"), Decimal("25.00")),
    ],
)
def test_accuracy_transformation_is_deterministic_bounded_and_rounded_half_up(
    acpl: Decimal, accuracy: Decimal
) -> None:
    result = AccuracyPolicy().transform(acpl)

    assert result == accuracy
    assert Decimal(0) <= result <= Decimal(100)


def test_accuracy_transformation_is_monotonic_over_bounded_property_matrix() -> None:
    policy = AccuracyPolicy()
    values = tuple(policy.transform(Decimal(acpl)) for acpl in range(0, 1001))

    assert values[0] == Decimal("100.00")
    assert all(left >= right for left, right in zip(values, values[1:], strict=False))
    assert all(Decimal(0) <= value <= Decimal(100) for value in values)


def test_fractional_acpl_uses_half_up_two_decimal_contract() -> None:
    moves = (
        _classified_move(ply=1, mover=chess.WHITE, before_cp=10, after_cp=9),
        _classified_move(ply=3, mover=chess.WHITE, before_cp=10, after_cp=8),
    )
    summary = GameMetricAggregationService().aggregate(_classified_game(moves)).white

    assert summary.summed_centipawn_loss == 3
    assert summary.acpl == Decimal("1.50")
    assert summary.accuracy == Decimal("98.52")


@pytest.mark.parametrize(
    ("total", "eligible", "expected"),
    [
        (0, 0, None),
        (1, 0, Decimal("0.00")),
        (3, 1, Decimal("33.33")),
        (3, 2, Decimal("66.67")),
        (3, 3, Decimal("100.00")),
    ],
)
def test_cpl_coverage_zero_denominator_and_ratio_property_matrix(
    total: int,
    eligible: int,
    expected: Decimal | None,
) -> None:
    moves = tuple(
        _classified_move(
            ply=index + 1,
            mover=chess.WHITE,
            before_cp=20 if index < eligible else None,
            after_cp=20 if index < eligible else None,
            before_mate=None if index < eligible else 3,
            after_mate=None if index < eligible else 2,
            reference=None,
        )
        for index in range(total)
    )
    summary = GameMetricAggregationService().aggregate(_classified_game(moves)).white

    assert summary.total_move_count == total
    assert summary.cpl_eligible_move_count == eligible
    assert summary.excluded_move_count == total - eligible
    assert summary.cpl_coverage == expected


def test_aggregation_is_order_independent_and_immutable() -> None:
    moves = _game_moves()
    service = GameMetricAggregationService()
    first = service.aggregate(_classified_game(moves))
    second_input = _classified_game(tuple(reversed(moves)))
    second_input = InternalClassifiedMoveMetrics(
        game_id=first.game_id,
        analysis_run_id=first.analysis_run_id,
        lease_generation=first.lease_generation,
        moves=second_input.moves,
    )
    second = service.aggregate(second_input)

    assert first == second
    field_name = "white"
    with pytest.raises(FrozenInstanceError):
        setattr(first, field_name, first.black)
    assert isinstance(first, InternalGameAnalyticalAggregate)
