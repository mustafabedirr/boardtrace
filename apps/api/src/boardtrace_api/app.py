from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from boardtrace_api.api.v1.router import router as v1_router
from boardtrace_api.config import Settings
from boardtrace_api.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from boardtrace_api.core.middleware import RequestIdMiddleware
from boardtrace_api.logging import configure_logging


def create_app(
    settings: Settings | None = None,
    extra_routers: Sequence[APIRouter] = (),
) -> FastAPI:
    resolved = settings or Settings()
    logger = configure_logging(resolved.log_level, resolved.log_format)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("application started", extra={"environment": resolved.environment.value})
        yield
        logger.info("application stopped", extra={"environment": resolved.environment.value})

    app = FastAPI(
        title="BoardTrace API",
        description="Backend API for post-game chess analysis.",
        version=resolved.app_version,
        lifespan=lifespan,
        openapi_tags=[{"name": "health", "description": "Application health."}],
    )
    app.state.settings = resolved
    app.exception_handler(ApiError)(api_error_handler)
    app.exception_handler(StarletteHTTPException)(http_error_handler)
    app.exception_handler(RequestValidationError)(validation_error_handler)
    app.exception_handler(Exception)(unexpected_error_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[resolved.request_id_header],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.trusted_hosts)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(v1_router, prefix=resolved.api_v1_prefix)
    for router in extra_routers:
        app.include_router(router)
    return app
