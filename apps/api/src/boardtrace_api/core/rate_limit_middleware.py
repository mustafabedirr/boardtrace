"""Production-only authentication and abuse-control middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from boardtrace_api.rate_limits import (
    ANALYSIS_START,
    AUTHENTICATED_GLOBAL,
    AUTHENTICATED_USER,
    FAILED_LOGIN,
    FAILED_LOGIN_BLOCK_SECONDS,
    HEALTH,
    MANUAL_RETRY,
    REDIS_RETRY_AFTER_SECONDS,
    CounterStore,
    RateLimitUnavailable,
    enforce,
    masked_identity,
)

HEALTH_PATHS = frozenset({"/health"})
AUTH_BOOTSTRAP_PATHS = frozenset(
    {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/extension-pairings/exchange"}
)


class ProductionRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, store: CounterStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client is not None else "unknown"
        try:
            if path in HEALTH_PATHS:
                retry = await enforce(self._store, HEALTH, masked_identity(client_ip), path)
                return _limited(retry) if retry is not None else await call_next(request)

            if path in AUTH_BOOTSTRAP_PATHS:
                block_key = f"boardtrace:rl:login-block:{masked_identity(client_ip)}"
                blocked_for = await self._store.get_ttl(block_key)
                if blocked_for > 0:
                    return _limited(blocked_for)
                response = await call_next(request)
                if path.endswith("/login") and response.status_code == 401:
                    retry = await enforce(
                        self._store, FAILED_LOGIN, masked_identity(client_ip), path
                    )
                    if retry is not None:
                        await self._store.block(block_key, FAILED_LOGIN_BLOCK_SECONDS)
                return response

            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or len(authorization) <= 7:
                return _error(401, "authentication_required")
            principal = masked_identity(authorization[7:])
            for limit, identity in (
                (AUTHENTICATED_GLOBAL, "all-authenticated-users"),
                (AUTHENTICATED_USER, principal),
            ):
                retry = await enforce(self._store, limit, identity, path)
                if retry is not None:
                    return _limited(retry)
            if request.method == "POST" and path == "/api/v1/games/ingestions":
                retry = await enforce(self._store, ANALYSIS_START, principal, path)
                if retry is not None:
                    return _limited(retry)
                payload: object = {}
                if request.headers.get("content-length") not in (None, "0"):
                    try:
                        payload = await request.json()
                    except ValueError:
                        return _error(422, "invalid_request")
                if isinstance(payload, dict) and payload.get("manual_retry") is True:
                    source_checksum = payload.get("source_checksum")
                    if not isinstance(source_checksum, str) or len(source_checksum) != 64:
                        return _error(422, "invalid_retry_fingerprint")
                    retry = await enforce(
                        self._store,
                        MANUAL_RETRY,
                        f"{principal}:{source_checksum}",
                        path,
                    )
                    if retry is not None:
                        return _limited(retry)
            return await call_next(request)
        except RateLimitUnavailable:
            return _error(503, "rate_limit_state_unavailable", REDIS_RETRY_AFTER_SECONDS)


def _limited(retry_after: int) -> JSONResponse:
    return _error(429, "rate_limit_exceeded", retry_after)


def _error(status: int, code: str, retry_after: int | None = None) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(max(1, retry_after))
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={"error": {"code": code, "message": "Request could not be completed."}},
    )
