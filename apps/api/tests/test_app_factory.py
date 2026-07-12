import httpx
import pytest
from fastapi import APIRouter

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings


def build_test_router() -> APIRouter:
    router = APIRouter()

    @router.get("/__test__/injected")
    def injected_route() -> dict[str, str]:
        return {"scope": "test-only"}

    return router


@pytest.mark.anyio
async def test_extra_router_is_isolated_in_routes_and_openapi() -> None:
    router = build_test_router()
    production = create_app(Settings())
    injected = create_app(Settings(), extra_routers=(router,))
    transport = httpx.ASGITransport(app=injected)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        injected_response = await client.get("/__test__/injected")
        schema = await client.get("/openapi.json")
    assert injected_response.json() == {"scope": "test-only"}
    assert injected is not production
    assert "/__test__/injected" in schema.json()["paths"]
    assert "/__test__/injected" not in production.openapi()["paths"]
    assert "/__test__/injected" not in create_app(Settings()).openapi()["paths"]
    production_paths = production.openapi()["paths"]
    assert "/analyze" not in production_paths
    assert "/best-move" not in production_paths
    assert "/engine" not in production_paths
