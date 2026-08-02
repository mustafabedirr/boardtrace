from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


def test_game_lifecycle_openapi_is_minimal_and_analysis_free() -> None:
    document = create_app(Settings()).openapi()
    operation = document["paths"]["/api/v1/games/{game_id}/lifecycle"]["get"]
    schema = document["components"]["schemas"]["PublicGameLifecycleResponse"]

    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "game_id",
        "lifecycle",
        "completion_verified",
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicGameLifecycleResponse"
    }
    serialized = str(operation) + str(schema)
    for forbidden in (
        "readiness",
        "result_available",
        "polling",
        "analysis_job",
        "analysis_run",
        "lease_generation",
        "worker",
        "engine",
        "moves",
        "accuracy",
    ):
        assert forbidden not in serialized
