import httpx
import pytest

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


@pytest.mark.anyio
async def test_liveness_response_matches_its_public_schema() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "service": "boardtrace-api",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"]
    assert "environment" not in response.json()
    assert "secret" not in response.text.lower()


@pytest.mark.anyio
async def test_readiness_response_matches_its_public_schema() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ready", "checks": {"application": "ok"}}
    assert response.headers["X-Request-ID"]
