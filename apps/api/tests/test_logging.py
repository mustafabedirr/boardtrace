import json
import logging
from io import StringIO

import httpx
import pytest
from fastapi import APIRouter
from pydantic import ValidationError

from boardtrace_api.app import create_app
from boardtrace_api.config import LogFormat, Settings
from boardtrace_api.logging import (
    DiagnosticMetadata,
    JsonFormatter,
    SafeDiagnosticFilter,
    configure_logging,
    request_id_context,
)


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
    assert payload["event"] == "request completed"
    assert payload["component"] == "boardtrace_api"
    assert "outcome" in payload
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


def test_json_formatter_escapes_untrusted_control_characters_into_one_event() -> None:
    record = logging.LogRecord(
        "boardtrace_api",
        logging.WARNING,
        "",
        0,
        'bounded\nforgery\r\t\u001b[31m{"event":"fake"}',
        (),
        None,
    )

    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert len(rendered.splitlines()) == 1
    assert payload["event"] == 'bounded\nforgery\r\t\u001b[31m{"event":"fake"}'
    assert payload["component"] == "boardtrace_api"


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
    assert payload["outcome"] == "success"
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


@pytest.mark.parametrize(
    "unsafe",
    (
        '[Event "Synthetic"]\n1. e4 e5 2. Nf3',
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        '{"initial_fen":"8/8/8/8/8/8/8/8 w - - 0 1"}',
        '{"moves":["e2e4","e7e5"]}',
        "Bearer synthetic-secret-token",
        "person@example.test",
        "192.0.2.44",
    ),
)
def test_central_filter_suppresses_unsafe_api_worker_and_outbox_content(unsafe: str) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SafeDiagnosticFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("boardtrace_api.worker")
    previous_handlers, previous_level, previous_propagate = (
        logger.handlers[:],
        logger.level,
        logger.propagate,
    )
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("outbox callback failed: %s", unsafe, extra={"operation": unsafe})
    finally:
        logger.handlers[:] = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
    rendered = stream.getvalue()
    assert unsafe not in rendered
    payload = json.loads(rendered)
    assert payload["event"] == "diagnostic_content_suppressed"
    assert payload["error_code"] == "unsafe_diagnostic_content"
    assert payload["outcome"] == "suppressed"


def test_typed_diagnostic_metadata_rejects_payloads_and_game_content() -> None:
    metadata = DiagnosticMetadata(
        job_id="8c6d4aac-768f-42a0-8fef-f33250211988",
        outcome="failed",
        game_checksum="a" * 64,
    )
    assert metadata.game_checksum == "a" * 64
    with pytest.raises(ValidationError, match="unsafe diagnostic content"):
        DiagnosticMetadata(error_code="moves=e2e4")
    with pytest.raises(ValidationError, match="Extra inputs"):
        DiagnosticMetadata.model_validate({"request_body": {"moves": ["e2e4"]}})


def test_server_identifier_with_move_like_uuid_segment_is_not_suppressed() -> None:
    job_id = "54b20902-b7a6-4c1d-9c80-9cf69d2aef77"
    metadata = DiagnosticMetadata(job_id=job_id)
    assert metadata.job_id == job_id

    record = logging.makeLogRecord(
        {"name": "boardtrace_api.analysis", "msg": "analysis_job_created", "job_id": job_id}
    )
    assert SafeDiagnosticFilter().filter(record)
    assert record.getMessage() == "analysis_job_created"
    assert record.__dict__["job_id"] == job_id


def test_server_identifier_still_rejects_game_fields_and_unbounded_characters() -> None:
    with pytest.raises(ValidationError, match="unsafe diagnostic content"):
        DiagnosticMetadata(job_id="moves=e2e4")
    with pytest.raises(ValidationError, match="unsafe diagnostic content"):
        DiagnosticMetadata(worker_id="worker with spaces")
