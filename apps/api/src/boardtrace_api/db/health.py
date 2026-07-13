import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("boardtrace_api")


async def database_ready(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError):
        logger.warning("database readiness check failed")
        return False
    return True
