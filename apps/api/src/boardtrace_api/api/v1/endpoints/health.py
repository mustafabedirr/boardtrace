from fastapi import APIRouter, Request

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
def ready() -> ReadinessResponse:
    return ReadinessResponse(status="ready", checks={"application": "ok"})
