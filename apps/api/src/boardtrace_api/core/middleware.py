import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from boardtrace_api.logging import request_id_context

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        value = request.headers.get(request.app.state.settings.request_id_header, "")
        request_id = value if _SAFE_REQUEST_ID.fullmatch(value) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logging.getLogger("boardtrace_api").info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "environment": request.app.state.settings.environment.value,
                },
            )
            response.headers[request.app.state.settings.request_id_header] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        finally:
            request_id_context.reset(token)
