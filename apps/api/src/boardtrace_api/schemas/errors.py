from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
