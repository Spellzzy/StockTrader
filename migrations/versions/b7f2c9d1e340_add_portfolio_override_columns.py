"""add portfolio override columns

Revision ID: b7f2c9d1e340
Revises: e5c805847a70
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7f2c9d1e340"
down_revision: Union[str, None] = "e5c805847a70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 需要 batch 模式；已通过 init_db() 补过列的库不受影响
    with op.batch_alter_table("portfolio", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "manual_override", sa.Boolean(), nullable=False,
            server_default=sa.text("0"), comment="是否手工校正并锁定",
        ))
        batch_op.add_column(sa.Column("override_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("override_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("portfolio", schema=None) as batch_op:
        batch_op.drop_column("override_at")
        batch_op.drop_column("override_note")
        batch_op.drop_column("manual_override")
