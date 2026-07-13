"""add authentication

Revision ID: 7f01a2b3c4d5
Revises: 06b908fae09f
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "7f01a2b3c4d5"
down_revision = "06b908fae09f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("normalized_email", sa.String(320), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(512), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE users SET normalized_email = lower(email) WHERE normalized_email IS NULL")
    op.alter_column("users", "normalized_email", nullable=False)
    op.create_unique_constraint("uq_users_normalized_email", "users", ["normalized_email"])
    op.create_index("ix_users_normalized_email", "users", ["normalized_email"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_digest", sa.String(128), nullable=False, unique=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "replaced_by_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        ),
    )
    for name, column in (
        ("ix_auth_sessions_user_id", "user_id"),
        ("ix_auth_sessions_expires_at", "expires_at"),
        ("ix_auth_sessions_revoked_at", "revoked_at"),
        ("ix_auth_sessions_family_id", "family_id"),
    ):
        op.create_index(name, "auth_sessions", [column])


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_normalized_email", table_name="users")
    op.drop_constraint("uq_users_normalized_email", "users", type_="unique")
    for column in (
        "password_changed_at",
        "last_login_at",
        "email_verified",
        "is_active",
        "password_hash",
        "normalized_email",
    ):
        op.drop_column("users", column)
