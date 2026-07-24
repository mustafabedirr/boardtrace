from pathlib import Path

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


def test_internal_analysis_read_contract_is_absent_from_openapi() -> None:
    document = create_app(Settings()).openapi()
    serialized = str(document)

    assert "InternalAnalysisSnapshot" not in serialized
    assert "PersistedCompleteAnalysisResult" not in serialized
    assert "principal_variation_uci" not in serialized
    assert "best_move_uci" not in serialized
    assert "MoveAnalyticalMetric" not in serialized
    assert "raw_centipawn_loss" not in serialized
    assert "ClassifiedMoveMetric" not in serialized
    assert "InternalClassifiedMoveMetrics" not in serialized
    assert "InternalGameAnalyticalAggregate" not in serialized
    assert "UnifiedInternalAnalysisAggregate" not in serialized
    assert "InternalAnalysisAggregateService" not in serialized
    assert "InternalAnalysisReadFacade" not in serialized
    assert "PlayerAnalyticalSummary" not in serialized
    assert "classification_coverage_percent" not in serialized
    assert "analysis_run_id" not in serialized
    assert "lease_generation" not in serialized
    assert "reference_best_move_uci" not in serialized
    assert "centipawn_delta" not in serialized


def test_api_and_public_schema_modules_do_not_import_internal_read_service() -> None:
    source_root = Path(__file__).parents[2] / "src" / "boardtrace_api"
    public_sources = tuple((source_root / "api").rglob("*.py")) + tuple(
        (source_root / "schemas").rglob("*.py")
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in public_sources)

    assert "analysis_reads" not in combined
    assert "InternalAnalysisReadService" not in combined
    assert "move_metrics" not in combined
    assert "MoveMetricDerivationService" not in combined
    assert "move_classification" not in combined
    assert "MoveClassificationService" not in combined
    assert "game_metrics" not in combined
    assert "GameMetricAggregationService" not in combined
    assert "analysis_aggregates" not in combined
    assert "InternalAnalysisAggregateService" not in combined
    assert "analysis_facade" not in combined
    assert "InternalAnalysisReadFacade" not in combined


def test_engine_execution_and_internal_results_remain_backend_only() -> None:
    repository_root = Path(__file__).parents[4]
    api_source = repository_root / "apps" / "api" / "src" / "boardtrace_api"
    client_roots = (
        repository_root / "apps" / "web",
        repository_root / "apps" / "extension" / "src",
        repository_root / "packages",
    )
    client_sources = tuple(
        path
        for root in client_roots
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"}
        and not {"node_modules", ".next", "dist", "build"}.intersection(path.parts)
    )
    engine_mentions = tuple(
        path
        for path in client_sources
        if any(
            token in path.read_text(encoding="utf-8").casefold()
            for token in (
                "stockfish",
                "bestmove",
                "best_move",
                "principalvariation",
                "principal_variation",
                "matescore",
                "mate_score",
            )
        )
    )
    assert engine_mentions == (repository_root / "apps" / "extension" / "src" / "protocol.ts",)
    extension_protocol = engine_mentions[0].read_text(encoding="utf-8")
    assert "FORBIDDEN_ANALYSIS_FIELD_NAMES" in extension_protocol
    assert "Engine-derived analysis fields are forbidden" in extension_protocol

    production_sources = tuple(api_source.rglob("*.py"))
    constructors = tuple(
        path
        for path in production_sources
        if "StockfishEngine(" in path.read_text(encoding="utf-8")
    )
    assert constructors == (api_source / "worker.py",)
