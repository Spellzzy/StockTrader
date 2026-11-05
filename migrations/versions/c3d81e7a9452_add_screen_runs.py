"""add screen_runs

Revision ID: c3d81e7a9452
Revises: b7f2c9d1e340
Create Date: 2026-11-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d81e7a9452"
down_revision: Union[str, None] = "b7f2c9d1e340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screen_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_date", sa.String(length=10), nullable=False),
        sa.Column("pool", sa.String(length=64), nullable=False),
        sa.Column("params_hash", sa.String(length=32), nullable=False),
        sa.Column("universe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("top_n", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_date", "params_hash", name="uq_screen_runs_date_params"),
    )
    op.create_index("ix_screen_runs_run_date", "screen_runs", ["run_date"])


def downgrade() -> None:
    op.drop_index("ix_screen_runs_run_date", table_name="screen_runs")
    op.drop_table("screen_runs")
