from pathlib import Path

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings

ALLOWED_RESPONSE_PROPERTIES = {"game_id", "moves", "white", "black"}
FORBIDDEN_OPENAPI_TERMS = {
    "UnifiedInternalAnalysisAggregate",
    "InternalAnalysisSnapshot",
    "InternalMoveMetrics",
    "InternalClassifiedMoveMetrics",
    "InternalGameAnalyticalAggregate",
    "analysis_run_id",
    "lease_generation",
    "analysis_version",
    "owner_user_id",
    "position_id",
    "engine_name",
    "engine_version",
    "configuration_snapshot",
    "best_move_uci",
    "principal_variation_uci",
    "reference_best_move_uci",
    "centipawn_delta",
    "raw_centipawn_loss",
    "mate_in",
}


def test_public_analysis_openapi_contains_only_explicit_dto_boundary() -> None:
    document = create_app(Settings()).openapi()
    operation = document["paths"]["/api/v1/analysis/games/{game_id}"]["get"]
    schema = document["components"]["schemas"]["PublicGameAnalysisResponse"]

    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == ALLOWED_RESPONSE_PROPERTIES
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicGameAnalysisResponse"
    }
    serialized = str(operation) + str(
        {
            name: value
            for name, value in document["components"]["schemas"].items()
            if name.startswith("Public")
        }
    )
    assert all(term not in serialized for term in FORBIDDEN_OPENAPI_TERMS)


def test_public_schema_has_no_internal_domain_imports() -> None:
    schema_path = (
        Path(__file__).parents[2] / "src" / "boardtrace_api" / "schemas" / "analysis_results.py"
    )
    source = schema_path.read_text(encoding="utf-8")

    assert "boardtrace_api.analysis" not in source
    assert "boardtrace_api.services" not in source
    assert "boardtrace_api.models" not in source
