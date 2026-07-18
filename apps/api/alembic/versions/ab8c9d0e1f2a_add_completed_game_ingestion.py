"""add completed game ingestion

Revision ID: ab8c9d0e1f2a
Revises: 9c3d4e5f6a7b
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "ab8c9d0e1f2a"
down_revision = "9c3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("source_game_id", sa.String(200), nullable=True))
    op.add_column("games", sa.Column("ingestion_key", sa.String(64), nullable=True))
    op.add_column("games", sa.Column("ingestion_payload_hash", sa.String(64), nullable=True))
    op.add_column("games", sa.Column("normalized_moves", postgresql.JSONB(), nullable=True))
    op.add_column(
        "games", sa.Column("completion_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_games_ingestion_key", "games", ["ingestion_key"], unique=True)
    op.create_unique_constraint(
        "uq_games_user_platform_source_game_id", "games", ["user_id", "platform", "source_game_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_games_user_platform_source_game_id", "games", type_="unique")
    op.drop_index("ix_games_ingestion_key", table_name="games")
    for column in (
        "completion_verified_at",
        "normalized_moves",
        "ingestion_payload_hash",
        "ingestion_key",
        "source_game_id",
    ):
        op.drop_column("games", column)
