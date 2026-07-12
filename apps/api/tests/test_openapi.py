import httpx
import pytest

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


@pytest.mark.anyio
async def test_openapi_exposes_public_health_and_error_contracts_only() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    schema = response.json()
    paths = schema["paths"]
    components = schema["components"]["schemas"]
    assert response.status_code == 200
    assert schema["info"]["title"] == "BoardTrace API"
    assert schema["info"]["version"] == "0.1.0"
    assert schema["info"]["description"] == "Backend API for post-game chess analysis."
    assert "/api/v1/health/live" in paths
    assert "/api/v1/health/ready" in paths
    assert "/analyze" not in paths
    assert "/best-move" not in paths
    assert "/engine" not in paths
    assert "/api/v1/games" not in paths
    assert "/api/v1/users" not in paths
    assert "/api/v1/database" not in paths
    assert not any(path.startswith("/__test__/") for path in paths)
    assert "HealthResponse" in components
    assert "ReadinessResponse" in components
    assert "ErrorResponse" in components
