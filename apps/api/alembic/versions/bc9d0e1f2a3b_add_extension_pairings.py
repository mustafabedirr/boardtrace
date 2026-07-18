"""add extension pairings

Revision ID: bc9d0e1f2a3b
Revises: ab8c9d0e1f2a
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "bc9d0e1f2a3b"
down_revision = "ab8c9d0e1f2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extension_pairings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_digest", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extension_id", sa.String(128), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_extension_pairings_user_id", "extension_pairings", ["user_id"])
    op.create_index("ix_extension_pairings_expires_at", "extension_pairings", ["expires_at"])
    op.create_index(
        "ix_extension_pairings_code_digest", "extension_pairings", ["code_digest"], unique=True
    )


def downgrade() -> None:
    op.drop_table("extension_pairings")
