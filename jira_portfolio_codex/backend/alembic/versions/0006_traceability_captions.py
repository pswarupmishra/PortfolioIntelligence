"""add configurable traceability level captions

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("traceability_configs") as batch_op:
        batch_op.add_column(sa.Column("level_captions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("traceability_configs") as batch_op:
        batch_op.drop_column("level_captions_json")
