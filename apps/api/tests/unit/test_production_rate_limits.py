from __future__ import annotations

from collections import defaultdict

import httpx
import pytest
from fastapi import FastAPI, Response

from boardtrace_api.core.rate_limit_middleware import ProductionRateLimitMiddleware
from boardtrace_api.rate_limits import (
    ANALYSIS_START,
    AUTHENTICATED_GLOBAL,
    AUTHENTICATED_USER,
    FAILED_LOGIN,
    HEALTH,
    RateLimitUnavailable,
)


class FakeCounterStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = defaultdict(int)
        self.windows: dict[str, int] = {}
        self.blocks: dict[str, int] = {}
        self.available = True

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        if not self.available:
            raise RateLimitUnavailable
        self.counts[key] += 1
        self.windows[key] = window_seconds
        return window_seconds if self.counts[key] > limit else None

    async def get_ttl(self, key: str) -> int:
        if not self.available:
            raise RateLimitUnavailable
        return self.blocks.get(key, 0)

    async def block(self, key: str, seconds: int) -> None:
        if not self.available:
            raise RateLimitUnavailable
        self.blocks[key] = seconds


def app_with_store(store: FakeCounterStore) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ProductionRateLimitMiddleware, store=store)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/games/ingestions")
    async def ingestion() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    async def login() -> Response:
        return Response(status_code=401)

    return app


@pytest.mark.anyio
async def test_policy_constants_match_r4() -> None:
    assert (AUTHENTICATED_USER.count, AUTHENTICATED_USER.window_seconds) == (30, 60)
    assert (AUTHENTICATED_GLOBAL.count, AUTHENTICATED_GLOBAL.window_seconds) == (120, 60)
    assert (ANALYSIS_START.count, ANALYSIS_START.window_seconds) == (3, 600)
    assert (FAILED_LOGIN.count, FAILED_LOGIN.window_seconds) == (10, 900)
    assert (HEALTH.count, HEALTH.window_seconds) == (30, 60)


@pytest.mark.anyio
async def test_anonymous_rejected_and_health_has_accurate_retry_after() -> None:
    store = FakeCounterStore()
    transport = httpx.ASGITransport(app=app_with_store(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/protected")).status_code == 401
        for _ in range(30):
            assert (await client.get("/health")).status_code == 200
        limited = await client.get("/health")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


@pytest.mark.anyio
async def test_user_and_analysis_start_limits_compose() -> None:
    store = FakeCounterStore()
    transport = httpx.ASGITransport(app=app_with_store(store))
    headers = {"Authorization": "Bearer user-one-token"}
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(3):
            assert (
                await client.post("/api/v1/games/ingestions", headers=headers)
            ).status_code == 200
        limited = await client.post("/api/v1/games/ingestions", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "600"


@pytest.mark.anyio
async def test_third_same_game_manual_retry_is_rejected() -> None:
    store = FakeCounterStore()
    transport = httpx.ASGITransport(app=app_with_store(store))
    headers = {"Authorization": "Bearer retry-user-token"}
    body = {"manual_retry": True, "source_checksum": "a" * 64}
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(2):
            response = await client.post("/api/v1/games/ingestions", headers=headers, json=body)
            assert response.status_code == 200
        limited = await client.post("/api/v1/games/ingestions", headers=headers, json=body)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "900"


@pytest.mark.anyio
async def test_global_limit_is_shared_across_distinct_users() -> None:
    store = FakeCounterStore()
    transport = httpx.ASGITransport(app=app_with_store(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for index in range(120):
            response = await client.get(
                "/api/v1/protected", headers={"Authorization": f"Bearer user-{index}"}
            )
            assert response.status_code == 200
        limited = await client.get(
            "/api/v1/protected", headers={"Authorization": "Bearer user-over-limit"}
        )
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


@pytest.mark.anyio
async def test_redis_failure_fails_closed_with_retry_after() -> None:
    store = FakeCounterStore()
    store.available = False
    transport = httpx.ASGITransport(app=app_with_store(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/protected", headers={"Authorization": "Bearer opaque-token"}
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert "opaque-token" not in response.text
