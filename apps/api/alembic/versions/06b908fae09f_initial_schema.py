"""initial_schema

Revision ID: 06b908fae09f
Revises:
Create Date: 2026-07-12 22:24:17.781442

"""

from collections.abc import Sequence

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

from alembic import op
from boardtrace_api.models import Game

# revision identifiers, used by Alembic.
revision: str = "06b908fae09f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Prompt 5 baseline from the current typed metadata.

    This historical revision predates authentication and completed-game
    ingestion.  The metadata is imported at migration runtime, so explicitly
    remove later additions before subsequent additive revisions introduce
    them in their own order.
    """
    bind = op.get_bind()
    Game.metadata.create_all(bind=bind)
    op.drop_table("analysis_move_evaluations")
    op.drop_table("analysis_position_evaluations")
    op.drop_table("analysis_runs")
    postgresql.ENUM(name="analysis_run_status").drop(bind, checkfirst=True)
    op.drop_table("extension_pairings")
    op.drop_table("auth_sessions")
    for column in (
        "completion_verified_at",
        "normalized_moves",
        "ingestion_payload_hash",
        "ingestion_key",
        "source_game_id",
    ):
        op.drop_column("games", column)
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
