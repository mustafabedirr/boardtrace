from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


def test_status_openapi_is_separate_bounded_and_result_free() -> None:
    document = create_app(Settings()).openapi()
    path = "/api/v1/analysis/games/{game_id}/status"
    operation = document["paths"][path]["get"]
    status_schema = document["components"]["schemas"]["PublicAnalysisStatusResponse"]
    polling_schema = document["components"]["schemas"]["PublicPollingGuidance"]
    readiness_schema = document["components"]["schemas"]["PublicAnalysisReadiness"]

    assert set(status_schema["properties"]) == {
        "game_id",
        "readiness",
        "result_available",
        "polling",
    }
    assert status_schema["additionalProperties"] is False
    assert set(polling_schema["properties"]) == {
        "should_retry",
        "retry_after_ms",
        "minimum_interval_ms",
        "maximum_interval_ms",
        "backoff_multiplier",
    }
    assert polling_schema["additionalProperties"] is False
    assert readiness_schema["enum"] == [
        "NOT_STARTED",
        "QUEUED",
        "RUNNING",
        "READY",
        "FAILED",
    ]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicAnalysisStatusResponse"
    }
    serialized = str(operation) + str(status_schema) + str(polling_schema)
    assert "PROCESSING" not in str(readiness_schema)
    assert "RETRYING" not in str(readiness_schema)
    assert "UNAVAILABLE" not in str(readiness_schema)
    for forbidden in (
        "PublicGameAnalysisResponse",
        "moves",
        "white",
        "black",
        "accuracy",
        "acpl",
        "quality",
        "centipawn",
        "job_id",
        "analysis_version",
        "lease_generation",
        "worker_id",
        "error_message",
    ):
        assert forbidden not in serialized
