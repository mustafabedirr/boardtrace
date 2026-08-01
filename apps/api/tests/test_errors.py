from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter
from pydantic import PostgresDsn, RedisDsn

from boardtrace_api.app import create_app
from boardtrace_api.config import Environment, LogFormat, Settings
from boardtrace_api.core.errors import ApiError


class AllowingCounterStore:
    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        return None

    async def get_ttl(self, key: str) -> int:
        return 0

    async def block(self, key: str, seconds: int) -> None:
        return None


def build_error_router() -> APIRouter:
    router = APIRouter()

    @router.get("/__test__/validation")
    def validation_route(value: int) -> dict[str, int]:
        return {"value": value}

    @router.get("/__test__/custom-error")
    def custom_error_route() -> None:
        raise ApiError("test_error", "Test-only error.", 418)

    @router.get("/__test__/unexpected-error")
    def unexpected_error_route() -> None:
        raise RuntimeError("internal test detail")

    return router


@pytest.mark.anyio
async def test_not_found_uses_the_standard_error_envelope() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/missing", headers={"X-Request-ID": "not-found"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "not-found"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "request_id": "not-found",
            "details": None,
        }
    }
    assert "routes" not in response.text.lower()


@pytest.mark.anyio
async def test_validation_error_uses_the_standard_error_envelope() -> None:
    app = create_app(Settings(), extra_routers=(build_error_router(),))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/__test__/validation?value=not-a-number",
            headers={"X-Request-ID": "validation-error"},
        )

    payload = response.json()["error"]
    assert response.status_code == 422
    assert payload["code"] == "validation_error"
    assert payload["request_id"] == "validation-error"
    assert response.headers["X-Request-ID"] == payload["request_id"]
    assert payload["details"] == [
        {
            "location": "query.value",
            "message": "Input should be a valid integer, unable to parse string as an integer",
        }
    ]


@pytest.mark.anyio
async def test_custom_api_error_uses_its_status_and_code() -> None:
    app = create_app(Settings(), extra_routers=(build_error_router(),))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/__test__/custom-error")

    assert response.status_code == 418
    assert response.json()["error"]["code"] == "test_error"
    assert isinstance(response.json()["error"]["request_id"], str)
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


@pytest.mark.anyio
async def test_unexpected_error_hides_internal_details_in_production(tmp_path: Path) -> None:
    stockfish = tmp_path / "stockfish"
    stockfish.write_text("fixture")
    stockfish.chmod(0o755)
    settings = Settings(
        environment=Environment.PRODUCTION,
        cors_allowed_origins=["https://web.example.test"],
        database_url=PostgresDsn(
            "postgresql+asyncpg://runtime:non-default@db.internal:5432/boardtrace"
        ),
        jwt_signing_secret="j" * 32,
        log_format=LogFormat.JSON,
        rate_limit_enabled=True,
        redis_url=RedisDsn("rediss://runtime@redis.internal:6379/0"),
        refresh_token_pepper="p" * 32,
        stockfish_path=str(stockfish),
        trusted_hosts=["api.example.test"],
    )
    app = create_app(
        settings,
        extra_routers=(build_error_router(),),
        rate_limit_store=AllowingCounterStore(),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://api.example.test"
    ) as client:
        response = await client.get(
            "/__test__/unexpected-error",
            headers={"Authorization": "Bearer test-only-opaque-principal"},
        )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "An internal server error occurred.",
        "request_id": response.headers["X-Request-ID"],
        "details": None,
    }
    assert "internal test detail" not in response.text
    assert "traceback" not in response.text.lower()
