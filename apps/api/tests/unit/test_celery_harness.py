from boardtrace_api.analysis.queue import ANALYSIS_QUEUE, ANALYSIS_TASK, OUTBOX_PUBLISH_TASK
from boardtrace_api.worker import celery_app
from tests.runtime.celery_harness import RuntimeCeleryHarness


def test_harness_creates_independent_apps_without_mutating_production_singleton() -> None:
    production_name = celery_app.main
    production_broker = str(celery_app.conf.broker_url)
    first = RuntimeCeleryHarness.create("redis://127.0.0.1:61001/0")
    second = RuntimeCeleryHarness.create("redis://127.0.0.1:61002/0")
    try:
        assert first.app is not second.app
        assert first.app.main != second.app.main
        assert str(first.app.conf.broker_url).endswith(":61001/0")
        assert str(second.app.conf.broker_url).endswith(":61002/0")
        assert celery_app.main == production_name
        assert str(celery_app.conf.broker_url) == production_broker
    finally:
        first.close()
        second.close()


def test_harness_mirrors_minimum_queue_contract_and_factories() -> None:
    harness = RuntimeCeleryHarness.create("redis://127.0.0.1:61003/0")
    try:
        assert harness.app.conf.task_serializer == "json"
        assert harness.app.conf.accept_content == ["json"]
        assert harness.app.conf.task_default_queue == ANALYSIS_QUEUE
        assert harness.app.conf.task_routes[ANALYSIS_TASK]["queue"] == ANALYSIS_QUEUE
        assert harness.app.conf.task_routes[OUTBOX_PUBLISH_TASK]["queue"] == ANALYSIS_QUEUE
        assert harness.app.conf.task_ignore_result is True
        assert harness.queue()._app is harness.app
    finally:
        harness.close()


def test_harness_close_is_idempotent() -> None:
    harness = RuntimeCeleryHarness.create("redis://127.0.0.1:61004/0")
    harness.close()
    harness.close()


def test_closed_harness_rejects_new_adapter_or_publisher_creation() -> None:
    harness = RuntimeCeleryHarness.create("redis://127.0.0.1:61005/0")
    harness.close()

    try:
        harness.queue()
    except RuntimeError as error:
        assert "closed" in str(error)
    else:
        raise AssertionError("closed harness created a queue adapter")
