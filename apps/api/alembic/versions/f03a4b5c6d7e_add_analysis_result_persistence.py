"""add analysis result persistence

Revision ID: f03a4b5c6d7e
Revises: ef2a3b4c5d6e
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f03a4b5c6d7e"
down_revision = "ef2a3b4c5d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_status = postgresql.ENUM(
        "COMPLETE", "PARTIAL", name="analysis_run_status", create_type=False
    )
    run_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("engine_name", sa.String(100), nullable=True),
        sa.Column("engine_version", sa.String(100), nullable=True),
        sa.Column("configuration_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("total_positions", sa.Integer(), nullable=False),
        sa.Column("evaluated_positions", sa.Integer(), nullable=False),
        sa.Column("total_moves", sa.Integer(), nullable=False),
        sa.Column("completed_moves", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_error_type", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("lease_generation > 0", name="lease_generation_positive"),
        sa.CheckConstraint("analysis_version > 0", name="analysis_version_positive"),
        sa.CheckConstraint("total_positions >= 0", name="total_positions_non_negative"),
        sa.CheckConstraint("evaluated_positions >= 0", name="evaluated_positions_non_negative"),
        sa.CheckConstraint("total_moves >= 0", name="total_moves_non_negative"),
        sa.CheckConstraint("completed_moves >= 0", name="completed_moves_non_negative"),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_job_id", "lease_generation", name="uq_analysis_runs_analysis_job_id"
        ),
    )
    op.create_index("ix_analysis_runs_analysis_job_id", "analysis_runs", ["analysis_job_id"])
    op.create_index("ix_analysis_runs_game_id", "analysis_runs", ["game_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
        "analysis_position_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("side_to_move", sa.String(1), nullable=False),
        sa.Column("centipawns", sa.Integer(), nullable=True),
        sa.Column("mate_in", sa.Integer(), nullable=True),
        sa.Column("best_move_uci", sa.String(5), nullable=False),
        sa.Column("principal_variation_uci", postgresql.JSONB(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=True),
        sa.Column("nodes", sa.Integer(), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ply >= 0", name="ply_non_negative"),
        sa.CheckConstraint(
            "(centipawns IS NULL) <> (mate_in IS NULL)",
            name="exactly_one_score",
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id", "ply", name="uq_analysis_position_evaluations_analysis_run_id"
        ),
    )
    op.create_index(
        "ix_analysis_position_evaluations_analysis_run_id",
        "analysis_position_evaluations",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_analysis_position_evaluations_source_position_id",
        "analysis_position_evaluations",
        ["source_position_id"],
    )

    op.create_table(
        "analysis_move_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("move_uci", sa.String(5), nullable=False),
        sa.Column("move_san", sa.String(20), nullable=False),
        sa.Column("before_position_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("after_position_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ply > 0", name="ply_positive"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["before_position_evaluation_id"],
            ["analysis_position_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["after_position_evaluation_id"],
            ["analysis_position_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id", "ply", name="uq_analysis_move_evaluations_analysis_run_id"
        ),
    )
    op.create_index(
        "ix_analysis_move_evaluations_analysis_run_id",
        "analysis_move_evaluations",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_analysis_move_evaluations_before_position_evaluation_id",
        "analysis_move_evaluations",
        ["before_position_evaluation_id"],
    )
    op.create_index(
        "ix_analysis_move_evaluations_after_position_evaluation_id",
        "analysis_move_evaluations",
        ["after_position_evaluation_id"],
    )


def downgrade() -> None:
    op.drop_table("analysis_move_evaluations")
    op.drop_table("analysis_position_evaluations")
    op.drop_table("analysis_runs")
    postgresql.ENUM(name="analysis_run_status").drop(op.get_bind(), checkfirst=True)
