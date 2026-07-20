"""add analysis job lease generation

Revision ID: ef2a3b4c5d6e
Revises: de1f2a3b4c5d
"""

import sqlalchemy as sa

from alembic import op

revision = "ef2a3b4c5d6e"
down_revision = "de1f2a3b4c5d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("analysis_jobs")}
    if "lease_generation" not in columns:
        op.add_column(
            "analysis_jobs",
            sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("analysis_jobs")}
    if "lease_generation" in columns:
        op.drop_column("analysis_jobs", "lease_generation")
