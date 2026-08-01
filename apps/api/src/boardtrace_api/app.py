from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from boardtrace_api.api.v1.router import router as v1_router
from boardtrace_api.config import Environment, Settings
from boardtrace_api.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from boardtrace_api.core.middleware import RequestIdMiddleware
from boardtrace_api.core.rate_limit_middleware import ProductionRateLimitMiddleware
from boardtrace_api.db.engine import create_database_engine
from boardtrace_api.logging import configure_logging
from boardtrace_api.queue_admission import (
    ImmediateQueueAdmission,
    QueueAdmissionController,
    RedisQueueAdmission,
)
from boardtrace_api.rate_limits import CounterStore, RedisCounterStore
from boardtrace_api.schemas.health import MinimumHealthResponse


def create_app(
    settings: Settings | None = None,
    extra_routers: Sequence[APIRouter] = (),
    rate_limit_store: CounterStore | None = None,
    analysis_admission: QueueAdmissionController | None = None,
) -> FastAPI:
    resolved = settings or Settings()
    logger = configure_logging(resolved.log_level, resolved.log_format)
    shared_redis: Redis | None = None
    if resolved.environment is Environment.PRODUCTION and (
        rate_limit_store is None or analysis_admission is None
    ):
        shared_redis = Redis.from_url(str(resolved.redis_url), decode_responses=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("application started", extra={"environment": resolved.environment.value})
        try:
            yield
        finally:
            if shared_redis is not None:
                await shared_redis.aclose()
            await app.state.database_engine.dispose()
            logger.info("application stopped", extra={"environment": resolved.environment.value})

    app = FastAPI(
        title="BoardTrace API",
        description="Backend API for post-game chess analysis.",
        version=resolved.app_version,
        lifespan=lifespan,
        openapi_tags=[{"name": "health", "description": "Application health."}],
    )
    app.state.settings = resolved
    app.state.database_engine = create_database_engine(resolved)
    if analysis_admission is not None:
        app.state.analysis_admission = analysis_admission
    elif resolved.environment is Environment.PRODUCTION:
        if shared_redis is None:
            raise RuntimeError("production admission state was not initialized")
        app.state.analysis_admission = RedisQueueAdmission(shared_redis)
    else:
        app.state.analysis_admission = ImmediateQueueAdmission()
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
    if resolved.environment is Environment.PRODUCTION:
        store = rate_limit_store
        if store is None:
            if shared_redis is None:
                raise RuntimeError("production rate-limit store was not initialized")
            store = RedisCounterStore(shared_redis)
        app.add_middleware(ProductionRateLimitMiddleware, store=store)

    @app.get("/health", response_model=MinimumHealthResponse, include_in_schema=False)
    async def minimum_health() -> MinimumHealthResponse:
        return MinimumHealthResponse(status="ok")

    app.include_router(v1_router, prefix=resolved.api_v1_prefix)
    for router in extra_routers:
        app.include_router(router)
    return app
