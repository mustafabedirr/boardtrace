import json
import logging

import httpx
import pytest
from fastapi import APIRouter

from boardtrace_api.app import create_app
from boardtrace_api.config import LogFormat, Settings
from boardtrace_api.logging import JsonFormatter, configure_logging, request_id_context


def test_json_formatter_includes_request_id() -> None:
    token = request_id_context.set("request-123")
    try:
        record = logging.LogRecord(
            "boardtrace_api", logging.INFO, "", 0, "request completed", (), None
        )
        record.method = "GET"
        record.path = "/api/v1/health/live"
        record.status_code = 200
        record.duration_ms = 1.5
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(token)
    assert payload["request_id"] == "request-123"
    assert payload["method"] == "GET"
    assert "authorization" not in payload


def test_console_formatter_produces_readable_output() -> None:
    logger = configure_logging("INFO", "console")
    record = logging.LogRecord("boardtrace_api", logging.INFO, "", 0, "started", (), None)

    assert logger.handlers[0].format(record) == "INFO boardtrace_api started"


def test_json_formatter_only_emits_allowlisted_fields() -> None:
    record = logging.LogRecord("boardtrace_api", logging.INFO, "", 0, "safe message", (), None)
    record.authorization = "Bearer secret"
    record.request_body = "secret body"
    record.fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    record.screenshot = b"binary screenshot"

    payload = json.loads(JsonFormatter().format(record))

    assert "authorization" not in payload
    assert "request_body" not in payload
    assert "fen" not in payload
    assert "screenshot" not in payload
    assert "secret" not in json.dumps(payload)


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.messages: list[str] = []
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        self.messages.append(self.format(record))


def collect_boardtrace_records() -> tuple[logging.Logger, RecordCollector]:
    logger = configure_logging("INFO", "json")
    collector = RecordCollector()
    logger.addHandler(collector)
    return logger, collector


def build_failing_router() -> APIRouter:
    router = APIRouter()

    @router.get("/__test__/logging-error")
    def failing_route() -> None:
        raise RuntimeError("internal test detail")

    return router


def test_logging_configuration_does_not_duplicate_handlers() -> None:
    configure_logging("INFO", "json")
    logger = configure_logging("INFO", "json")

    assert len(logger.handlers) == 1


@pytest.mark.anyio
async def test_request_completion_log_has_context_and_safe_fields() -> None:
    app = create_app(Settings(log_format=LogFormat.JSON))
    logger, collector = collect_boardtrace_records()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.get("/api/v1/health/live", headers={"X-Request-ID": "logging-test"})
    finally:
        logger.removeHandler(collector)

    payload = next(
        json.loads(message)
        for record, message in zip(collector.records, collector.messages, strict=True)
        if record.msg == "request completed"
    )
    assert payload["request_id"] == "logging-test"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/health/live"
    assert payload["status_code"] == 200
    assert isinstance(payload["duration_ms"], float)
    assert payload["environment"] == "development"


@pytest.mark.anyio
async def test_lifespan_logs_start_and_stop_events() -> None:
    app = create_app(Settings(log_format=LogFormat.JSON))
    logger, collector = collect_boardtrace_records()
    try:
        async with app.router.lifespan_context(app):
            pass
    finally:
        logger.removeHandler(collector)

    assert [record.msg for record in collector.records] == [
        "application started",
        "application stopped",
    ]


@pytest.mark.anyio
async def test_unexpected_error_is_logged_without_internal_details() -> None:
    app = create_app(
        Settings(log_format=LogFormat.JSON),
        extra_routers=(build_failing_router(),),
    )
    logger, collector = collect_boardtrace_records()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/__test__/logging-error")
    finally:
        logger.removeHandler(collector)

    payload = next(
        json.loads(message)
        for record, message in zip(collector.records, collector.messages, strict=True)
        if record.msg == "unexpected API error"
    )
    assert response.status_code == 500
    assert payload["request_id"] == response.json()["error"]["request_id"]
    assert "internal test detail" not in json.dumps(payload)
