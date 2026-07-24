from dataclasses import FrozenInstanceError, fields, replace

import chess
import pytest

from boardtrace_api.analysis.move_metrics import (
    MoveAnalyticalMetric,
    MoveMetricDerivationError,
    MoveMetricInput,
    MoveMetricOutcome,
    NormalizedScoreKind,
    derive_move_metric,
)
from boardtrace_api.analysis.stockfish import StockfishScore


def _input(
    before: StockfishScore | None,
    after: StockfishScore | None,
    *,
    mover: chess.Color = chess.WHITE,
    terminal: bool = False,
) -> MoveMetricInput:
    return MoveMetricInput(
        ply=1,
        move_uci="e2e4",
        move_san="e4",
        reference_best_move_uci="e2e4",
        mover=mover,
        before_side_to_move=mover,
        after_side_to_move=not mover,
        before_score=before,
        after_score=after,
        after_is_terminal=terminal,
    )


def test_centipawn_loss_uses_mover_perspective() -> None:
    metric = derive_move_metric(
        _input(StockfishScore(centipawns=50), StockfishScore(centipawns=30))
    )

    assert metric.before.centipawns == 50
    assert metric.after.centipawns == -30
    assert metric.centipawn_delta == -80
    assert metric.raw_centipawn_loss == 80
    assert metric.centipawn_loss == 80
    assert not metric.negative_loss_clamped


def test_improvement_has_positive_delta_negative_raw_loss_and_zero_clamped_loss() -> None:
    metric = derive_move_metric(
        _input(StockfishScore(centipawns=20), StockfishScore(centipawns=-50))
    )

    assert metric.centipawn_delta == 30
    assert metric.raw_centipawn_loss == -30
    assert metric.centipawn_loss == 0
    assert metric.negative_loss_clamped


@pytest.mark.parametrize(
    "before_cp,after_side_cp,expected_delta,expected_raw_loss,expected_loss",
    [
        (25, -25, 0, 0, 0),
        (50, 30, -80, 80, 80),
        (20, -50, 30, -30, 0),
    ],
)
def test_signed_delta_and_raw_loss_are_exact_additive_inverses(
    before_cp: int,
    after_side_cp: int,
    expected_delta: int,
    expected_raw_loss: int,
    expected_loss: int,
) -> None:
    metric = derive_move_metric(
        _input(
            StockfishScore(centipawns=before_cp),
            StockfishScore(centipawns=after_side_cp),
        )
    )

    assert metric.centipawn_delta == expected_delta
    assert metric.raw_centipawn_loss == expected_raw_loss
    assert metric.centipawn_loss == expected_loss
    assert metric.raw_centipawn_loss == -metric.centipawn_delta


def test_black_mover_normalization_is_symmetric() -> None:
    metric = derive_move_metric(
        _input(
            StockfishScore(centipawns=100),
            StockfishScore(centipawns=20),
            mover=chess.BLACK,
        )
    )

    assert metric.before.centipawns == 100
    assert metric.after.centipawns == -20
    assert metric.centipawn_delta == -120
    assert metric.raw_centipawn_loss == 120
    assert metric.centipawn_loss == 120


@pytest.mark.parametrize(
    ("before", "after", "outcome", "before_kind", "after_kind"),
    [
        (
            StockfishScore(mate_in=3),
            StockfishScore(mate_in=-2),
            MoveMetricOutcome.MATE_TO_MATE,
            NormalizedScoreKind.MATE,
            NormalizedScoreKind.MATE,
        ),
        (
            StockfishScore(centipawns=40),
            StockfishScore(mate_in=-2),
            MoveMetricOutcome.CENTIPAWN_TO_MATE,
            NormalizedScoreKind.CENTIPAWN,
            NormalizedScoreKind.MATE,
        ),
        (
            StockfishScore(mate_in=3),
            StockfishScore(centipawns=-40),
            MoveMetricOutcome.MATE_TO_CENTIPAWN,
            NormalizedScoreKind.MATE,
            NormalizedScoreKind.CENTIPAWN,
        ),
        (
            None,
            StockfishScore(centipawns=-40),
            MoveMetricOutcome.MISSING_SCORE,
            NormalizedScoreKind.MISSING,
            NormalizedScoreKind.CENTIPAWN,
        ),
    ],
)
def test_non_centipawn_transitions_have_explicit_non_cpl_outcomes(
    before: StockfishScore | None,
    after: StockfishScore,
    outcome: MoveMetricOutcome,
    before_kind: NormalizedScoreKind,
    after_kind: NormalizedScoreKind,
) -> None:
    metric = derive_move_metric(_input(before, after))

    assert metric.outcome is outcome
    assert metric.before.kind is before_kind
    assert metric.after.kind is after_kind
    assert metric.centipawn_delta is None
    assert metric.raw_centipawn_loss is None
    assert metric.centipawn_loss is None
    assert not metric.negative_loss_clamped


def test_mate_score_is_negated_from_after_side_to_mover_perspective() -> None:
    metric = derive_move_metric(_input(StockfishScore(mate_in=4), StockfishScore(mate_in=2)))

    assert metric.before.mate_in == 4
    assert metric.after.mate_in == -2


def test_terminal_position_is_explicit_metadata_without_inventing_cpl_semantics() -> None:
    metric = derive_move_metric(
        _input(StockfishScore(mate_in=1), StockfishScore(mate_in=-1), terminal=True)
    )

    assert metric.after_is_terminal
    assert metric.outcome is MoveMetricOutcome.MATE_TO_MATE
    assert metric.centipawn_loss is None


def test_position_binding_and_metric_contract_fail_closed_and_are_immutable() -> None:
    value = _input(StockfishScore(centipawns=0), StockfishScore(centipawns=0))
    invalid = replace(value, after_side_to_move=value.mover)
    with pytest.raises(MoveMetricDerivationError):
        derive_move_metric(invalid)

    metric = derive_move_metric(value)
    field_name = "centipawn_loss"
    with pytest.raises(FrozenInstanceError):
        setattr(metric, field_name, 1)
    assert isinstance(metric, MoveAnalyticalMetric)


def test_metric_contract_contains_no_label_accuracy_or_aggregate_policy() -> None:
    field_names = {field.name for field in fields(MoveAnalyticalMetric)}

    assert field_names.isdisjoint(
        {
            "classification",
            "label",
            "quality",
            "accuracy",
            "acpl",
            "threshold",
            "game_summary",
            "player_summary",
        }
    )
