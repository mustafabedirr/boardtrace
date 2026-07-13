"""align authentication unique indexes

Revision ID: 9c3d4e5f6a7b
Revises: 7f01a2b3c4d5
"""

from alembic import op

revision = "9c3d4e5f6a7b"
down_revision = "7f01a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_users_normalized_email", "users", type_="unique")
    op.drop_index("ix_users_normalized_email", table_name="users")
    op.create_index("ix_users_normalized_email", "users", ["normalized_email"], unique=True)
    op.drop_constraint("uq_auth_sessions_token_digest", "auth_sessions", type_="unique")
    op.create_index("ix_auth_sessions_token_digest", "auth_sessions", ["token_digest"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_token_digest", table_name="auth_sessions")
    op.create_unique_constraint("uq_auth_sessions_token_digest", "auth_sessions", ["token_digest"])
    op.drop_index("ix_users_normalized_email", table_name="users")
    op.create_unique_constraint("uq_users_normalized_email", "users", ["normalized_email"])
    op.create_index("ix_users_normalized_email", "users", ["normalized_email"])
