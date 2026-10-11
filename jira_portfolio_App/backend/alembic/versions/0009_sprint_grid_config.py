"""add separate sprint grid configuration

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sprint_grid_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_jira_id", sa.String(100), nullable=False),
        sa.Column("optional_fields_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_jira_id"], ["jira_projects.jira_project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_jira_id"),
    )
    op.create_index("ix_sprint_grid_configs_project", "sprint_grid_configs", ["project_jira_id"])


def downgrade() -> None:
    op.drop_table("sprint_grid_configs")
