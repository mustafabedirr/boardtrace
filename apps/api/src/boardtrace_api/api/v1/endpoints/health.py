from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from boardtrace_api.db.health import database_ready
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    responses={422: {"model": ErrorResponse}},
)
def live(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(status="ok", service="boardtrace-api", version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={422: {"model": ErrorResponse}},
)
async def ready(request: Request) -> ReadinessResponse | JSONResponse:
    if await database_ready(request.app.state.database_engine):
        return ReadinessResponse(status="ready", checks={"application": "ok", "database": "ok"})
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": {"application": "ok", "database": "unavailable"}},
    )
