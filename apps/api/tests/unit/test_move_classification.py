from dataclasses import FrozenInstanceError

import chess
import pytest

from boardtrace_api.analysis.move_classification import (
    CentipawnLossThresholdPolicy,
    ClassificationReason,
    ClassifiedMoveMetric,
    MoveClassificationService,
    MoveQuality,
)
from boardtrace_api.analysis.move_metrics import (
    MoveAnalyticalMetric,
    MoveMetricInput,
    derive_move_metric,
)
from boardtrace_api.analysis.stockfish import StockfishScore


def _metric(
    *,
    before_cp: int | None = None,
    after_cp: int | None = None,
    before_mate: int | None = None,
    after_mate: int | None = None,
    played: str = "e2e4",
    reference: str | None = "d2d4",
) -> MoveAnalyticalMetric:
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
    return derive_move_metric(
        MoveMetricInput(
            ply=1,
            move_uci=played,
            move_san="e4",
            reference_best_move_uci=reference,
            mover=chess.WHITE,
            before_side_to_move=chess.WHITE,
            after_side_to_move=chess.BLACK,
            before_score=before,
            after_score=after,
            after_is_terminal=False,
        )
    )


@pytest.mark.parametrize(
    ("loss", "quality"),
    [
        (0, MoveQuality.EXCELLENT),
        (20, MoveQuality.EXCELLENT),
        (21, MoveQuality.GOOD),
        (50, MoveQuality.GOOD),
        (51, MoveQuality.INACCURACY),
        (100, MoveQuality.INACCURACY),
        (101, MoveQuality.MISTAKE),
        (200, MoveQuality.MISTAKE),
        (201, MoveQuality.BLUNDER),
    ],
)
def test_threshold_boundaries_are_lower_exclusive_and_upper_inclusive(
    loss: int, quality: MoveQuality
) -> None:
    metric = _metric(before_cp=1000, after_cp=1000 - loss)
    classified = MoveClassificationService().classify_move(metric)

    assert classified.quality is quality
    assert classified.reason is ClassificationReason.CENTIPAWN_THRESHOLD


def test_threshold_policy_is_monotonic_over_bounded_property_matrix() -> None:
    policy = CentipawnLossThresholdPolicy()
    rank = {
        MoveQuality.EXCELLENT: 0,
        MoveQuality.GOOD: 1,
        MoveQuality.INACCURACY: 2,
        MoveQuality.MISTAKE: 3,
        MoveQuality.BLUNDER: 4,
    }
    qualities = tuple(policy.classify(loss) for loss in range(0, 401))

    assert all(
        rank[left] <= rank[right] for left, right in zip(qualities, qualities[1:], strict=False)
    )


def test_exact_canonical_uci_best_move_equality_precedes_cp_threshold() -> None:
    metric = _metric(
        before_cp=500,
        after_cp=-500,
        played="e7e8q",
        reference="e7e8q",
    )
    classified = MoveClassificationService().classify_move(metric)

    assert classified.best_move_equal
    assert classified.quality is MoveQuality.BEST
    assert classified.reason is ClassificationReason.BEST_MOVE_EQUALITY


@pytest.mark.parametrize(
    ("before_cp", "after_cp", "before_mate", "after_mate", "quality", "reason"),
    [
        (
            0,
            None,
            None,
            3,
            MoveQuality.BEST,
            ClassificationReason.FORCED_WIN_CREATED,
        ),
        (
            0,
            None,
            None,
            -3,
            MoveQuality.BLUNDER,
            ClassificationReason.FORCED_LOSS_ENTERED,
        ),
        (
            None,
            0,
            3,
            None,
            MoveQuality.BLUNDER,
            ClassificationReason.FORCED_WIN_LOST,
        ),
        (
            None,
            0,
            -3,
            None,
            MoveQuality.BEST,
            ClassificationReason.FORCED_LOSS_ESCAPED,
        ),
        (
            None,
            None,
            3,
            -2,
            MoveQuality.BLUNDER,
            ClassificationReason.MATE_POLARITY_FLIPPED_TO_LOSS,
        ),
        (
            None,
            None,
            -3,
            2,
            MoveQuality.BEST,
            ClassificationReason.MATE_POLARITY_FLIPPED_TO_WIN,
        ),
    ],
)
def test_decisive_mate_transitions_have_precedence(
    before_cp: int | None,
    after_cp: int | None,
    before_mate: int | None,
    after_mate: int | None,
    quality: MoveQuality,
    reason: ClassificationReason,
) -> None:
    metric = _metric(
        before_cp=before_cp,
        after_cp=after_cp,
        before_mate=before_mate,
        after_mate=after_mate,
        played="e2e4",
        reference="e2e4",
    )
    classified = MoveClassificationService().classify_move(metric)

    assert classified.best_move_equal
    assert classified.quality is quality
    assert classified.reason is reason


@pytest.mark.parametrize(("before_mate", "after_mate"), [(4, 3), (-4, -3)])
def test_best_equality_precedes_same_polarity_mate_fallback(
    before_mate: int, after_mate: int
) -> None:
    metric = _metric(
        before_mate=before_mate,
        after_mate=after_mate,
        played="e2e4",
        reference="e2e4",
    )

    classified = MoveClassificationService().classify_move(metric)

    assert classified.quality is MoveQuality.BEST
    assert classified.reason is ClassificationReason.BEST_MOVE_EQUALITY


@pytest.mark.parametrize(
    ("before_mate", "after_mate", "quality", "reason"),
    [
        (
            4,
            3,
            MoveQuality.GOOD,
            ClassificationReason.FORCED_WIN_PRESERVED,
        ),
        (
            -4,
            -3,
            MoveQuality.GOOD,
            ClassificationReason.FORCED_LOSS_UNRESOLVED,
        ),
        (
            0,
            3,
            MoveQuality.UNCLASSIFIED,
            ClassificationReason.MATE_POLARITY_UNCLASSIFIED,
        ),
    ],
)
def test_same_polarity_and_zero_mate_contract(
    before_mate: int,
    after_mate: int,
    quality: MoveQuality,
    reason: ClassificationReason,
) -> None:
    classified = MoveClassificationService().classify_move(
        _metric(before_mate=before_mate, after_mate=after_mate)
    )

    assert classified.quality is quality
    assert classified.reason is reason


@pytest.mark.parametrize(
    ("before_mate", "after_mate", "reason"),
    [
        (4, 3, ClassificationReason.FORCED_WIN_PRESERVED),
        (-4, -3, ClassificationReason.FORCED_LOSS_UNRESOLVED),
    ],
)
def test_same_polarity_missing_reference_is_good(
    before_mate: int,
    after_mate: int,
    reason: ClassificationReason,
) -> None:
    classified = MoveClassificationService().classify_move(
        _metric(
            before_mate=before_mate,
            after_mate=after_mate,
            reference=None,
        )
    )

    assert not classified.best_move_equal
    assert classified.quality is MoveQuality.GOOD
    assert classified.reason is reason


def test_missing_score_is_explicitly_unavailable() -> None:
    classified = MoveClassificationService().classify_move(
        _metric(
            before_cp=None,
            after_cp=0,
            before_mate=None,
            played="e2e4",
            reference="e2e4",
        )
    )

    assert classified.best_move_equal
    assert classified.quality is MoveQuality.UNCLASSIFIED
    assert classified.reason is ClassificationReason.SCORE_UNCLASSIFIED


@pytest.mark.parametrize(
    ("before_cp", "after_cp", "before_mate", "after_mate", "reason"),
    [
        (0, None, None, 3, ClassificationReason.FORCED_WIN_CREATED),
        (None, 0, -3, None, ClassificationReason.FORCED_LOSS_ESCAPED),
        (
            None,
            None,
            -3,
            2,
            ClassificationReason.MATE_POLARITY_FLIPPED_TO_WIN,
        ),
    ],
)
def test_positive_mate_transitions_require_exact_reference_for_best(
    before_cp: int | None,
    after_cp: int | None,
    before_mate: int | None,
    after_mate: int | None,
    reason: ClassificationReason,
) -> None:
    service = MoveClassificationService()
    non_reference = service.classify_move(
        _metric(
            before_cp=before_cp,
            after_cp=after_cp,
            before_mate=before_mate,
            after_mate=after_mate,
            played="e2e4",
            reference="d2d4",
        )
    )
    reference = service.classify_move(
        _metric(
            before_cp=before_cp,
            after_cp=after_cp,
            before_mate=before_mate,
            after_mate=after_mate,
            played="e2e4",
            reference="e2e4",
        )
    )

    assert non_reference.quality is MoveQuality.EXCELLENT
    assert not non_reference.best_move_equal
    assert non_reference.reason is reason
    assert reference.quality is MoveQuality.BEST
    assert reference.best_move_equal
    assert reference.reason is reason


def test_best_is_never_emitted_without_exact_reference_equality_property() -> None:
    service = MoveClassificationService()
    metrics = (
        _metric(before_cp=100, after_cp=100, reference="d2d4"),
        _metric(before_cp=0, after_mate=3, reference="d2d4"),
        _metric(before_mate=-3, after_cp=0, reference="d2d4"),
        _metric(before_mate=-3, after_mate=2, reference="d2d4"),
        _metric(before_mate=4, after_mate=3, reference="d2d4"),
        _metric(before_mate=-4, after_mate=-3, reference="d2d4"),
    )

    classified = tuple(service.classify_move(metric) for metric in metrics)

    assert all(move.quality is not MoveQuality.BEST or move.best_move_equal for move in classified)


def test_classification_is_deterministic_and_immutable() -> None:
    service = MoveClassificationService()
    metric = _metric(before_cp=100, after_cp=49)

    first = service.classify_move(metric)
    second = service.classify_move(metric)

    assert first == second
    field_name = "quality"
    with pytest.raises(FrozenInstanceError):
        setattr(first, field_name, MoveQuality.BEST)
    assert isinstance(first, ClassifiedMoveMetric)


def test_legacy_unavailable_label_and_reasons_are_absent() -> None:
    quality_tokens = set(MoveQuality.__members__) | {item.value for item in MoveQuality}
    reason_tokens = {item.value for item in ClassificationReason}
    legacy_token = "UN" + "AVAILABLE"

    assert all(legacy_token not in token for token in quality_tokens)
    assert all(legacy_token not in token for token in reason_tokens)
    assert MoveQuality.UNCLASSIFIED.value == "UNCLASSIFIED"
