import httpx
import pytest

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


@pytest.mark.anyio
async def test_security_and_request_id_headers_are_applied() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "middleware-test"}
        )

    assert response.headers["X-Request-ID"] == "middleware-test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.anyio
async def test_cors_allows_configured_origin_and_rejects_other_origins() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed = await client.get(
            "/api/v1/health/live", headers={"Origin": "http://localhost:3000"}
        )
        denied = await client.get(
            "/api/v1/health/live", headers={"Origin": "https://untrusted.example"}
        )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.anyio
async def test_cors_preflight_allows_only_configured_cross_origin_requests() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "x-request-id" in response.headers["access-control-allow-headers"].lower()
    assert response.headers.get("access-control-allow-credentials") != "true"


@pytest.mark.anyio
async def test_request_without_origin_does_not_receive_cors_headers() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/live")

    assert "access-control-allow-origin" not in response.headers
