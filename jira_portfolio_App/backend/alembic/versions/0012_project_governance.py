"""Add project RAG status and management support.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_plans", sa.Column("project_status", sa.String(length=10), nullable=True))
    op.add_column("project_plans", sa.Column("management_support", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("project_plans", "management_support")
    op.drop_column("project_plans", "project_status")
