import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)

_PGN_TAG = re.compile(r"\[(?:Event|Site|Date|Round|White|Black|Result)\s+\"", re.IGNORECASE)
_FEN = re.compile(r"(?:[prnbqkPRNBQK1-8]+/){7}[prnbqkPRNBQK1-8]+\s+[wb]\s+")
_UCI_MOVE = re.compile(r"(?<![a-z0-9])[a-h][1-8][a-h][1-8][qrbn]?(?![a-z0-9])", re.I)
_GAME_FIELD = re.compile(
    r"(?:request_body|initial_fen|normalized_moves|principal_variation|best_move|full_pgn|\"pgn\"|\"moves\")\s*[:=]",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SECRET = re.compile(
    r"(?:bearer\s+[A-Za-z0-9._~+/=-]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)
_SERVER_IDENTIFIER_FIELDS = frozenset(
    {
        "request_id",
        "job_id",
        "correlation_id",
        "worker_id",
        "worker_task_id",
        "outbox_event_id",
    }
)
_SAFE_SERVER_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")


class DiagnosticMetadata(BaseModel):
    """The only metadata fields accepted by lifecycle diagnostic events."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=128)
    job_id: str | None = Field(default=None, max_length=64)
    correlation_id: str | None = Field(default=None, max_length=64)
    worker_id: str | None = Field(default=None, max_length=255)
    worker_task_id: str | None = Field(default=None, max_length=255)
    outbox_event_id: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=64)
    attempt_count: int | None = Field(default=None, ge=0)
    delivery_generation: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=100)
    duration_seconds: float | None = Field(default=None, ge=0)
    outcome: str | None = Field(default=None, max_length=64)
    queue_transition: str | None = Field(default=None, max_length=64)
    queue_position: int | None = Field(default=None, ge=1, le=3)
    timeout_reason: str | None = Field(default=None, max_length=100)
    cleanup_result: str | None = Field(default=None, max_length=64)
    provenance_result: str | None = Field(default=None, max_length=64)
    engine_invoked: bool | None = None
    live_game_guard: str | None = Field(default=None, max_length=64)
    game_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("*", mode="before")
    @classmethod
    def reject_unsafe_content(cls, value: object, info: ValidationInfo) -> object:
        server_identifier = info.field_name in _SERVER_IDENTIFIER_FIELDS
        if (
            server_identifier
            and isinstance(value, str)
            and not _SAFE_SERVER_IDENTIFIER.fullmatch(value)
        ):
            raise ValueError("unsafe diagnostic content")
        if contains_unsafe_diagnostic_content(value, detect_uci_move=not server_identifier):
            raise ValueError("unsafe diagnostic content")
        return value


def contains_unsafe_diagnostic_content(value: object, *, detect_uci_move: bool = True) -> bool:
    if isinstance(value, (list, tuple, set, dict, bytes, bytearray)):
        return True
    if not isinstance(value, str):
        return False
    patterns = [_PGN_TAG, _FEN, _GAME_FIELD, _EMAIL, _IPV4, _SECRET]
    if detect_uci_move:
        patterns.append(_UCI_MOVE)
    return any(pattern.search(value) is not None for pattern in patterns)


class SafeDiagnosticFilter(logging.Filter):
    """Suppress an entire record when any emitted content violates log policy."""

    _standard_fields = frozenset(logging.makeLogRecord({}).__dict__)

    def filter(self, record: logging.LogRecord) -> bool:
        unsafe_message = contains_unsafe_diagnostic_content(record.getMessage())
        unsafe_context = any(
            contains_unsafe_diagnostic_content(
                value, detect_uci_move=key not in _SERVER_IDENTIFIER_FIELDS
            )
            for key, value in record.__dict__.items()
            if key not in self._standard_fields
        )
        if not unsafe_message and not unsafe_context:
            return True
        record.msg = "diagnostic_content_suppressed"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        for key in tuple(record.__dict__):
            if key not in self._standard_fields:
                del record.__dict__[key]
        record.error_code = "unsafe_diagnostic_content"
        record.outcome = "suppressed"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record_request_id = getattr(record, "request_id", None)
        request_id = (
            record_request_id if isinstance(record_request_id, str) else request_id_context.get()
        )
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "component": record.name,
            "outcome": getattr(record, "outcome", None),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
        }
        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "environment",
            "job_id",
            "correlation_id",
            "worker_task_id",
            "outbox_event_id",
            "status",
            "attempt_count",
            "worker_id",
            "delivery_generation",
            "error_code",
            "operation",
            "error_type",
            "observer_error_type",
            "masked_identity",
            "endpoint",
            "limit_category",
            "retention_days",
            "queue_transition",
            "queue_position",
            "timeout_reason",
            "cleanup_result",
            "provenance_result",
            "engine_invoked",
            "live_game_guard",
            "game_checksum",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str, log_format: str) -> logging.Logger:
    logger = logging.getLogger("boardtrace_api")
    logger.setLevel(level.upper())
    logger.handlers.clear()
    logger.filters.clear()
    logger.addFilter(SafeDiagnosticFilter())
    handler = logging.StreamHandler()
    handler.addFilter(SafeDiagnosticFilter())
    handler.setFormatter(
        JsonFormatter()
        if log_format == "json"
        else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
