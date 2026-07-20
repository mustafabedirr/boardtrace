"""Bounded, test-only controllers for real runtime dependencies."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from celery import Celery


def _run_docker(*arguments: str, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments], text=True, capture_output=True, check=False, timeout=timeout
    )


@dataclass
class RedisContainerController:
    """Controls one localhost-only, volume-free Redis test container."""

    name: str
    host_port: int
    container_id: str | None = field(default=None, init=False)

    def start(self) -> None:
        if self.inspect_state() == "running":
            return
        result = _run_docker(
            "run",
            "--name",
            self.name,
            "-p",
            f"127.0.0.1:{self.host_port}:6379",
            "-d",
            "redis:7-alpine",
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        )
        if result.returncode != 0:
            raise RuntimeError("Redis test container did not start")
        self.container_id = result.stdout.strip()
        self.wait_ready()

    def inspect_state(self) -> str | None:
        result = _run_docker("inspect", "--format", "{{.State.Status}}", self.name)
        return result.stdout.strip() if result.returncode == 0 else None

    def wait_ready(self, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.host_port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Redis test container readiness timed out")

    def stop(self) -> None:
        if self.inspect_state() != "running":
            return
        result = _run_docker("stop", "--time", "5", self.name)
        if result.returncode != 0:
            raise RuntimeError("Redis test container did not stop")
        self.wait_unavailable()

    def wait_unavailable(self, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.host_port), timeout=0.25):
                    time.sleep(0.05)
            except OSError:
                return
        raise RuntimeError("Redis test container stayed reachable after stop")

    def restart(self) -> None:
        if self.inspect_state() == "running":
            self.stop()
        result = _run_docker("start", self.name)
        if result.returncode != 0:
            raise RuntimeError("Redis test container did not restart")
        self.wait_ready()

    def remove(self) -> None:
        if self.inspect_state() is None:
            return
        result = _run_docker("rm", "--force", self.name)
        if result.returncode != 0:
            raise RuntimeError("Redis test container cleanup failed")
        self.container_id = None


@dataclass
class CeleryWorkerController:
    """Controls a real Celery subprocess without exposing its environment."""

    database_url: str
    extra_environment: Mapping[str, str] = field(default_factory=dict)
    app: Celery | None = None
    worker_hostname: str = field(
        default_factory=lambda: f"boardtrace-runtime-{uuid4().hex}@%h", init=False
    )
    process: subprocess.Popen[str] | None = field(default=None, init=False)

    def _control_app(self) -> Celery:
        if self.app is not None:
            return self.app
        from boardtrace_api.worker import celery_app

        return celery_app

    def start(self) -> int:
        if self.process is not None and self.process.poll() is None:
            return self.process.pid
        environment = (
            os.environ
            | {"BOARDTRACE_DATABASE_URL": self.database_url}
            | dict(self.extra_environment)
        )
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "boardtrace_api.worker:celery_app",
                "worker",
                "--pool=solo",
                "--loglevel=WARNING",
                f"--hostname={self.worker_hostname}",
            ],
            cwd="apps/api",
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        self.wait_ready()
        return self.process.pid

    def wait_ready(self, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                raise RuntimeError("Celery worker exited before readiness")
            if self._control_app().control.inspect(timeout=0.5).ping():
                return
            time.sleep(0.05)
        raise RuntimeError("Celery worker readiness timed out")

    def graceful_stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        self.wait_exit()

    def terminate(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        self.wait_exit()

    def kill(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.kill()
        self.wait_exit()

    def wait_exit(self, timeout: float = 10) -> None:
        if self.process is None:
            return
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)
        self.drain_output()

    def restart(self) -> int:
        previous_pid = self.process.pid if self.process is not None else None
        self.graceful_stop()
        pid = self.start()
        if previous_pid == pid:
            pytest.fail("Celery worker restart did not create a new process")
        return pid

    def drain_output(self) -> str:
        if self.process is None or self.process.stdout is None:
            return ""
        if self.process.poll() is None:
            return ""
        return self.process.communicate(timeout=1)[0]

    def assert_not_running(self) -> None:
        if self.process is not None and self.process.poll() is None:
            pytest.fail("Celery worker process is still running")
