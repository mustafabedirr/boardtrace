from sqlalchemy import CheckConstraint, UniqueConstraint

from boardtrace_api.db.base import Base
from boardtrace_api.models import Game
from boardtrace_api.models.enums import GameStatus


def test_persistence_metadata_contains_expected_tables() -> None:
    assert Game.metadata is Base.metadata
    assert set(Base.metadata.tables) == {
        "analysis_jobs",
        "auth_sessions",
        "detected_moves",
        "engine_analyses",
        "engine_versions",
        "game_frames",
        "games",
        "model_versions",
        "positions",
        "users",
    }


def test_game_status_enum_is_explicit_and_stable() -> None:
    assert [status.value for status in GameStatus] == [
        "CREATED",
        "CAPTURING",
        "FINISH_PENDING",
        "FINISHED",
        "DEEP_ANALYSIS_RUNNING",
        "ANALYSIS_AVAILABLE",
        "FAILED",
    ]


def test_position_constraints_are_present() -> None:
    constraints = Base.metadata.tables["positions"].constraints
    assert any(
        isinstance(constraint, UniqueConstraint)
        and set(constraint.columns.keys()) == {"game_id", "ply"}
        for constraint in constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_positions_detection_confidence_range"
        for constraint in constraints
    )
