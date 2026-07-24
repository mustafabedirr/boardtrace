"""Executable durable-FEN boundary for Prompt 10-C analysis results."""

from dataclasses import fields
from pathlib import Path

from boardtrace_api.analysis.full_game import EngineReusePolicy
from boardtrace_api.db.base import Base
from boardtrace_api.services.analysis_results import (
    EngineConfigurationSnapshot,
    PersistedPositionEvaluation,
)


def test_analysis_result_schema_and_read_model_exclude_raw_fen() -> None:
    analysis_table = Base.metadata.tables["analysis_position_evaluations"]

    assert "fen" not in analysis_table.c
    assert "fen" not in {field.name for field in fields(PersistedPositionEvaluation)}


def test_engine_snapshot_cannot_contain_raw_fen() -> None:
    snapshot = EngineConfigurationSnapshot(
        schema_version=1,
        depth=12,
        max_position_time_ms=250,
        max_game_time_ms=5_000,
        max_positions=100,
        max_moves=99,
        threads=1,
        hash_mb=16,
        command_timeout_ms=5_000,
        reuse_policy=EngineReusePolicy.SINGLE_PROCESS_PER_GAME,
    ).as_json()

    assert all("fen" not in key.casefold() for key in snapshot)
    assert all("fen" not in str(value).casefold() for value in snapshot.values())


def test_only_legacy_game_capture_tables_have_durable_fen_columns() -> None:
    durable_fen_columns = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.c
        if "fen" in column.name.casefold()
    }

    assert durable_fen_columns == {"games.initial_fen", "positions.fen"}


def test_analysis_persistence_implementation_has_no_fen_or_fingerprint_payload() -> None:
    source_root = Path(__file__).parents[2] / "src" / "boardtrace_api"
    persistence_sources = (
        source_root / "repositories" / "analysis_results.py",
        source_root / "services" / "analysis_results.py",
    )

    combined = "\n".join(path.read_text(encoding="utf-8") for path in persistence_sources)
    lowered = combined.casefold()
    assert "fen" not in lowered
    assert "fingerprint" not in lowered
