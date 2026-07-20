"""Explicit final transaction ownership for composed persistence workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

Result = TypeVar("Result")


class BeforeCommitHook(Protocol):
    """Runs after mutations are staged and immediately before final commit."""

    async def __call__(self) -> None: ...


async def no_op_before_commit() -> None:
    """Production default; tests may inject a deterministic composition hook."""


def get_before_commit_hook() -> BeforeCommitHook:
    """Production composition provider; FastAPI tests may override this dependency."""

    return no_op_before_commit


class TransactionBoundary:
    """Repositories stage mutations; this boundary alone commits or rolls back."""

    def __init__(
        self, session: AsyncSession, before_commit: BeforeCommitHook = no_op_before_commit
    ) -> None:
        self._session = session
        self._before_commit = before_commit

    async def execute(self, operation: Callable[[], Awaitable[Result]]) -> Result:
        try:
            result = await operation()
            await self._before_commit()
            await self._session.commit()
            return result
        except BaseException:
            await self._session.rollback()
            raise
