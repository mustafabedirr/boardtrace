import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from tests.postgres_helpers import create_test_engine, get_test_database_url

pytestmark = [pytest.mark.integration, pytest.mark.database, pytest.mark.migration]


def migration_config() -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    return config


def test_empty_database_upgrade_downgrade_and_reupgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = get_test_database_url()
    monkeypatch.setenv("BOARDTRACE_DATABASE_URL", url)
    command.downgrade(migration_config(), "base")

    tables_after_downgrade = asyncio.run(public_table_names())
    assert tables_after_downgrade == {"alembic_version"}

    command.upgrade(migration_config(), "head")
    revision, metadata_type = asyncio.run(revision_and_metadata_type())
    assert revision == "f03a4b5c6d7e"
    assert metadata_type == "jsonb"
    assert "extension_pairings" in asyncio.run(public_table_names())
    assert "analysis_job_outbox" in asyncio.run(public_table_names())
    assert "analysis_runs" in asyncio.run(public_table_names())
    assert "analysis_position_evaluations" in asyncio.run(public_table_names())
    assert "analysis_move_evaluations" in asyncio.run(public_table_names())


async def public_table_names() -> set[str]:
    engine = create_test_engine()
    async with engine.connect() as connection:
        rows = await connection.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        names = set(rows.all())
    await engine.dispose()
    return names


async def revision_and_metadata_type() -> tuple[str | None, str | None]:
    engine = create_test_engine()
    async with engine.connect() as connection:
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        metadata_type = await connection.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'model_versions' AND column_name = 'metadata'"
            )
        )
    await engine.dispose()
    return revision, metadata_type
