"""add analysis admission correlation

Revision ID: g14b5c6d7e8f
Revises: f03a4b5c6d7e
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "g14b5c6d7e8f"
down_revision = "f03a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column("admission_correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE analysis_jobs SET admission_correlation_id = id")
    op.alter_column("analysis_jobs", "admission_correlation_id", nullable=False)
    op.create_index(
        "ix_analysis_jobs_admission_correlation_id",
        "analysis_jobs",
        ["admission_correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_admission_correlation_id", table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "admission_correlation_id")
