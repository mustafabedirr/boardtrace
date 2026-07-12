import httpx
import pytest

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


@pytest.mark.anyio
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "testserver"])
async def test_default_trusted_hosts_are_accepted(host: str) -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url=f"http://{host}") as client:
        response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.anyio
async def test_disallowed_host_is_rejected() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://untrusted.example"
    ) as client:
        response = await client.get("/api/v1/health/live")
    assert response.status_code == 400
    assert "traceback" not in response.text.lower()


@pytest.mark.anyio
async def test_cors_with_allowed_host() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health/live", headers={"Origin": "http://localhost:3000"}
        )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
