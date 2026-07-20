from celery import Celery

from tests.runtime.controllers import CeleryWorkerController


def test_controllers_keep_injected_apps_and_hostnames_isolated() -> None:
    first_app = Celery("runtime-controller-first", broker="redis://127.0.0.1:61006/0")
    second_app = Celery("runtime-controller-second", broker="redis://127.0.0.1:61007/0")
    first = CeleryWorkerController("postgresql+asyncpg://test/first", app=first_app)
    second = CeleryWorkerController("postgresql+asyncpg://test/second", app=second_app)
    try:
        assert first._control_app() is first_app
        assert second._control_app() is second_app
        assert first.worker_hostname != second.worker_hostname
        assert "redis" not in first.worker_hostname
        assert "redis" not in second.worker_hostname
    finally:
        first_app.close()
        second_app.close()
