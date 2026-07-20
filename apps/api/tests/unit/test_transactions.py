import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.db.transactions import TransactionBoundary


class SessionSpy:
    def __init__(self, events: list[str], commit_error: BaseException | None = None) -> None:
        self.events = events
        self.commit_error = commit_error

    async def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")


def operation(events: list[str], result: str = "result") -> Callable[[], Awaitable[str]]:
    async def run() -> str:
        events.append("operation")
        return result

    return run


@pytest.mark.asyncio
async def test_transaction_boundary_commits_after_hook() -> None:
    events: list[str] = []

    async def hook() -> None:
        events.append("hook")

    session = SessionSpy(events)
    result = await TransactionBoundary(cast(AsyncSession, session), hook).execute(operation(events))
    assert result == "result"
    assert events == ["operation", "hook", "commit"]


@pytest.mark.asyncio
async def test_transaction_boundary_rolls_back_operation_failure() -> None:
    events: list[str] = []
    error = RuntimeError("operation failure")

    async def fail() -> str:
        events.append("operation")
        raise error

    session = SessionSpy(events)
    with pytest.raises(RuntimeError) as raised:
        await TransactionBoundary(cast(AsyncSession, session)).execute(fail)
    assert raised.value is error
    assert events == ["operation", "rollback"]


@pytest.mark.asyncio
async def test_transaction_boundary_rolls_back_hook_failure() -> None:
    events: list[str] = []
    error = RuntimeError("hook failure")

    async def hook() -> None:
        events.append("hook")
        raise error

    session = SessionSpy(events)
    with pytest.raises(RuntimeError) as raised:
        await TransactionBoundary(cast(AsyncSession, session), hook).execute(operation(events))
    assert raised.value is error
    assert events == ["operation", "hook", "rollback"]


@pytest.mark.asyncio
async def test_transaction_boundary_rolls_back_commit_failure() -> None:
    events: list[str] = []
    error = RuntimeError("commit failure")
    session = SessionSpy(events, error)
    with pytest.raises(RuntimeError) as raised:
        await TransactionBoundary(cast(AsyncSession, session)).execute(operation(events))
    assert raised.value is error
    assert events == ["operation", "commit", "rollback"]


@pytest.mark.asyncio
async def test_transaction_boundary_propagates_cancellation() -> None:
    events: list[str] = []

    async def cancel() -> str:
        events.append("operation")
        raise asyncio.CancelledError()

    session = SessionSpy(events)
    with pytest.raises(asyncio.CancelledError):
        await TransactionBoundary(cast(AsyncSession, session)).execute(cancel)
    assert events == ["operation", "rollback"]
