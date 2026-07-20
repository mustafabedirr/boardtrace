import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record_request_id = getattr(record, "request_id", None)
        request_id = (
            record_request_id if isinstance(record_request_id, str) else request_id_context.get()
        )
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
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
            "status",
            "attempt_count",
            "worker_id",
            "delivery_generation",
            "error_code",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str, log_format: str) -> logging.Logger:
    logger = logging.getLogger("boardtrace_api")
    logger.setLevel(level.upper())
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if log_format == "json"
        else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
