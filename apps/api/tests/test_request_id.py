import asyncio
import re

import httpx
import pytest

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings
from boardtrace_api.logging import request_id_context


@pytest.mark.anyio
async def test_request_id_is_generated_and_context_is_cleaned_up() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/live")

    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["X-Request-ID"])
    assert request_id_context.get() is None


@pytest.mark.anyio
async def test_valid_client_request_id_is_preserved_on_success_and_error() -> None:
    request_id = "client-request-123"
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        success = await client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})
        error = await client.get("/missing", headers={"X-Request-ID": request_id})

    assert success.headers["X-Request-ID"] == request_id
    assert error.headers["X-Request-ID"] == request_id
    assert error.json()["error"]["request_id"] == request_id


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_request_id", ["", "x" * 129, "invalid\nvalue"])
async def test_invalid_client_request_id_is_replaced(invalid_request_id: str) -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health/live", headers={"X-Request-ID": invalid_request_id}
        )

    assert response.headers["X-Request-ID"] != invalid_request_id
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["X-Request-ID"])


@pytest.mark.anyio
async def test_concurrent_requests_keep_request_ids_isolated() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        async def request(request_id: str) -> str:
            response = await client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})
            return response.headers["X-Request-ID"]

        request_ids = [f"parallel-{number}" for number in range(10)]
        responses = await asyncio.gather(*(request(value) for value in request_ids))

    assert responses == request_ids
