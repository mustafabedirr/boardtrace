import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from boardtrace_api.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger("boardtrace_api")


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code, self.message, self.status_code = code, message, status_code


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else "unknown"


def error_response(
    request: Request,
    *,
    status_code: int,
    content: ErrorResponse,
) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=content.model_dump(mode="json"))
    settings = request.app.state.settings
    response.headers[settings.request_id_header] = request_id(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(
        request,
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message, request_id=request_id(request))
        ),
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    message = (
        "The requested resource was not found."
        if exc.status_code == 404
        else "Request could not be completed."
    )
    return error_response(
        request,
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, request_id=request_id(request))
        ),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"location": ".".join(str(item) for item in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(
        request,
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed.",
                request_id=request_id(request),
                details=details,
            )
        ),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unexpected API error", extra={"request_id": request_id(request)})
    return error_response(
        request,
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                code="internal_error",
                message="An internal server error occurred.",
                request_id=request_id(request),
            )
        ),
    )
