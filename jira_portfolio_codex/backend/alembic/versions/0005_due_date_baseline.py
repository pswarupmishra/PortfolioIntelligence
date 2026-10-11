"""add due date baseline and changelog facts

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.add_column(sa.Column("baseline_due_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_issues_baseline_due_at", ["baseline_due_at"], unique=False)
    op.create_table(
        "issue_date_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("jira_field_id", sa.String(length=200), nullable=False),
        sa.Column("changelog_id", sa.String(length=100), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author_account_id", sa.String(length=200), nullable=True),
        sa.Column("from_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("to_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("issue_id", "jira_field_id", "changelog_id", name="uq_issue_date_changelog"),
    )
    op.create_index("ix_issue_date_changes_issue_id", "issue_date_changes", ["issue_id"])
    op.create_index("ix_issue_date_changes_jira_field_id", "issue_date_changes", ["jira_field_id"])
    op.create_index("ix_issue_date_changes_changed_at", "issue_date_changes", ["changed_at"])


def downgrade() -> None:
    op.drop_index("ix_issue_date_changes_changed_at", table_name="issue_date_changes")
    op.drop_index("ix_issue_date_changes_jira_field_id", table_name="issue_date_changes")
    op.drop_index("ix_issue_date_changes_issue_id", table_name="issue_date_changes")
    op.drop_table("issue_date_changes")
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_index("ix_issues_baseline_due_at")
        batch_op.drop_column("baseline_due_at")
