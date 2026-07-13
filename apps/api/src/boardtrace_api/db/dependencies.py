from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.db.session import create_session_factory


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = create_session_factory(request.app.state.database_engine)
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
