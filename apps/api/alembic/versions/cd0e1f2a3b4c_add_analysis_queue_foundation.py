"""add analysis queue foundation

Revision ID: cd0e1f2a3b4c
Revises: bc9d0e1f2a3b
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "cd0e1f2a3b4c"
down_revision = "bc9d0e1f2a3b"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for value in ("QUEUED", "CLAIMED", "RETRY_SCHEDULED"):
        op.execute(f"ALTER TYPE analysis_job_status ADD VALUE IF NOT EXISTS '{value}'")

    existing = _columns("analysis_jobs")
    additions = (
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("analysis_profile", sa.String(50), server_default="standard", nullable=False),
        sa.Column("analysis_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column("worker_id", sa.String(255), nullable=True),
        sa.Column("queue_message_id", sa.String(255), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("analysis_jobs", column)
    op.execute(
        "UPDATE analysis_jobs SET owner_user_id = games.user_id "
        "FROM games WHERE analysis_jobs.game_id = games.id AND owner_user_id IS NULL"
    )
    op.alter_column("analysis_jobs", "owner_user_id", nullable=False)

    inspector = sa.inspect(op.get_bind())
    constraints = {item["name"] for item in inspector.get_unique_constraints("analysis_jobs")}
    if "uq_analysis_jobs_game_id" not in constraints:
        op.create_unique_constraint(
            "uq_analysis_jobs_game_id",
            "analysis_jobs",
            ["game_id", "analysis_profile", "analysis_version"],
        )
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("analysis_jobs")}
    if "fk_analysis_jobs_owner_user_id_users" not in foreign_keys:
        op.create_foreign_key(
            "fk_analysis_jobs_owner_user_id_users",
            "analysis_jobs",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="CASCADE",
        )
    indexes = {item["name"] for item in inspector.get_indexes("analysis_jobs")}
    index_specs = {
        "ix_analysis_jobs_owner_user_id": ["owner_user_id"],
        "ix_analysis_jobs_lease_expires_at": ["lease_expires_at"],
        "ix_analysis_jobs_next_attempt_at": ["next_attempt_at"],
        "ix_analysis_jobs_queue_message_id": ["queue_message_id"],
        "ix_analysis_jobs_status_next_attempt_at": ["status", "next_attempt_at"],
        "ix_analysis_jobs_status_lease_expires_at": ["status", "lease_expires_at"],
    }
    for name, columns in index_specs.items():
        if name not in indexes:
            op.create_index(name, "analysis_jobs", columns)

    tables = set(inspector.get_table_names())
    if "analysis_job_outbox" not in tables:
        outbox_status = postgresql.ENUM(
            "PENDING", "PUBLISHED", name="analysis_outbox_status", create_type=False
        )
        outbox_status.create(op.get_bind(), checkfirst=True)
        op.create_table(
            "analysis_job_outbox",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("payload_version", sa.Integer(), nullable=False),
            sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", outbox_status, nullable=False),
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_code", sa.String(100), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["analysis_job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "analysis_job_id",
                "event_type",
                "payload_version",
                name="uq_analysis_job_outbox_analysis_job_id",
            ),
        )
        op.create_index(
            "ix_analysis_job_outbox_analysis_job_id", "analysis_job_outbox", ["analysis_job_id"]
        )
        op.create_index(
            "ix_analysis_job_outbox_correlation_id", "analysis_job_outbox", ["correlation_id"]
        )
        op.create_index("ix_analysis_job_outbox_status", "analysis_job_outbox", ["status"])
        op.create_index(
            "ix_analysis_job_outbox_status_next_attempt_at",
            "analysis_job_outbox",
            ["status", "next_attempt_at"],
        )


def downgrade() -> None:
    op.drop_table("analysis_job_outbox")
    postgresql.ENUM(name="analysis_outbox_status").drop(op.get_bind(), checkfirst=True)
    for name in (
        "ix_analysis_jobs_status_lease_expires_at",
        "ix_analysis_jobs_status_next_attempt_at",
        "ix_analysis_jobs_queue_message_id",
        "ix_analysis_jobs_next_attempt_at",
        "ix_analysis_jobs_lease_expires_at",
        "ix_analysis_jobs_owner_user_id",
    ):
        op.drop_index(name, table_name="analysis_jobs")
    op.drop_constraint(
        "uq_analysis_jobs_game_id",
        "analysis_jobs",
        type_="unique",
    )
    op.drop_constraint("fk_analysis_jobs_owner_user_id_users", "analysis_jobs", type_="foreignkey")
    for column in (
        "version",
        "queue_message_id",
        "worker_id",
        "last_error_message",
        "last_error_code",
        "next_attempt_at",
        "failed_at",
        "completed_at",
        "heartbeat_at",
        "lease_expires_at",
        "claimed_at",
        "analysis_version",
        "analysis_profile",
        "max_attempts",
        "attempt_count",
        "owner_user_id",
    ):
        op.drop_column("analysis_jobs", column)
