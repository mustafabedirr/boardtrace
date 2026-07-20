"""add analysis outbox delivery generation

Revision ID: de1f2a3b4c5d
Revises: cd0e1f2a3b4c
"""

import sqlalchemy as sa

from alembic import op

revision = "de1f2a3b4c5d"
down_revision = "cd0e1f2a3b4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("analysis_job_outbox")
    }
    if "delivery_generation" not in columns:
        op.add_column(
            "analysis_job_outbox",
            sa.Column("delivery_generation", sa.Integer(), server_default="0", nullable=False),
        )
    unique_constraints = sa.inspect(op.get_bind()).get_unique_constraints("analysis_job_outbox")
    current = next(
        (
            item
            for item in unique_constraints
            if item["name"] == "uq_analysis_job_outbox_analysis_job_id"
        ),
        None,
    )
    if current is not None and current["column_names"] != [
        "analysis_job_id",
        "event_type",
        "payload_version",
        "delivery_generation",
    ]:
        op.drop_constraint(
            "uq_analysis_job_outbox_analysis_job_id", "analysis_job_outbox", type_="unique"
        )
    if current is None or current["column_names"] != [
        "analysis_job_id",
        "event_type",
        "payload_version",
        "delivery_generation",
    ]:
        op.create_unique_constraint(
            "uq_analysis_job_outbox_analysis_job_id",
            "analysis_job_outbox",
            ["analysis_job_id", "event_type", "payload_version", "delivery_generation"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_analysis_job_outbox_analysis_job_id", "analysis_job_outbox", type_="unique"
    )
    op.create_unique_constraint(
        "uq_analysis_job_outbox_analysis_job_id",
        "analysis_job_outbox",
        ["analysis_job_id", "event_type", "payload_version"],
    )
    op.drop_column("analysis_job_outbox", "delivery_generation")
