"""add project plans and end-date baseline history

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_jira_id", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_jira_id"], ["jira_projects.jira_project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_jira_id"),
    )
    op.create_index("ix_project_plans_project_jira_id", "project_plans", ["project_jira_id"], unique=True)
    op.create_table(
        "project_plan_baselines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_plan_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_plan_id"], ["project_plans.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_plan_id", "version", name="uq_project_plan_baseline_version"),
    )
    op.create_index("ix_project_plan_baselines_project_plan_id", "project_plan_baselines", ["project_plan_id"])


def downgrade() -> None:
    op.drop_table("project_plan_baselines")
    op.drop_table("project_plans")
