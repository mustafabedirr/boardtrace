"""initial_schema

Revision ID: 06b908fae09f
Revises:
Create Date: 2026-07-12 22:24:17.781442

"""

from collections.abc import Sequence

from sqlalchemy.engine import Connection

from alembic import op
from boardtrace_api.models import Game

# revision identifiers, used by Alembic.
revision: str = "06b908fae09f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the reviewed PostgreSQL schema from the typed metadata."""
    bind = op.get_bind()
    Game.metadata.create_all(bind=bind)
    op.drop_table("auth_sessions")
    for column in (
        "password_changed_at",
        "last_login_at",
        "email_verified",
        "is_active",
        "password_hash",
        "normalized_email",
    ):
        op.drop_column("users", column)


def downgrade() -> None:
    """Drop all persistence tables and their PostgreSQL enum types."""
    bind: Connection = op.get_bind()
    Game.metadata.drop_all(bind=bind)
