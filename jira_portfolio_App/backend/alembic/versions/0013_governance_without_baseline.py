"""Permit project governance records before baseline dates exist.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_plans") as batch_op:
        batch_op.alter_column("start_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    # Projects with only governance data have no start date, so downgrade
    # requires those records to be completed or removed before enforcing NOT NULL.
    with op.batch_alter_table("project_plans") as batch_op:
        batch_op.alter_column("start_date", existing_type=sa.Date(), nullable=False)
