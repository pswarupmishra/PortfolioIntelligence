"""phase 2 issue sync and hierarchy

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("projects_json", sa.JSON(), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("upserted_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("anomaly_count", sa.Integer(), nullable=False),
        sa.Column("error_json", sa.JSON()),
        sa.Column("watermark_before", sa.DateTime(timezone=True)),
        sa.Column("watermark_after", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_issue_id", sa.String(100), nullable=False, unique=True),
        sa.Column("issue_key", sa.String(100), nullable=False),
        sa.Column("project_jira_id", sa.String(100), sa.ForeignKey("jira_projects.jira_project_id"), nullable=False),
        sa.Column("issue_type_jira_id", sa.String(100)),
        sa.Column("status_jira_id", sa.String(100)),
        sa.Column("parent_jira_issue_id", sa.String(100)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("assignee_account_id", sa.String(200)),
        sa.Column("reporter_account_id", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("raw_fields_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_sync_id", sa.Integer(), sa.ForeignKey("sync_runs.id")),
        sa.Column("is_deleted_or_inaccessible", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns, unique in [
        ("ix_issues_jira_issue_id", ["jira_issue_id"], True),
        ("ix_issues_issue_key", ["issue_key"], False),
        ("ix_issues_project_jira_id", ["project_jira_id"], False),
        ("ix_issues_issue_type_jira_id", ["issue_type_jira_id"], False),
        ("ix_issues_status_jira_id", ["status_jira_id"], False),
        ("ix_issues_parent_jira_issue_id", ["parent_jira_issue_id"], False),
        ("ix_issues_updated_at", ["updated_at"], False),
        ("ix_issues_last_seen_sync_id", ["last_seen_sync_id"], False),
        ("ix_issues_is_deleted_or_inaccessible", ["is_deleted_or_inaccessible"], False),
        ("ix_issues_project_parent", ["project_jira_id", "parent_jira_issue_id"], False),
    ]:
        op.create_index(name, "issues", columns, unique=unique)
    op.create_table(
        "issue_field_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jira_field_id", sa.String(200), nullable=False),
        sa.Column("element_index", sa.Integer(), nullable=False),
        sa.Column("value_type", sa.String(30), nullable=False),
        sa.Column("string_value", sa.Text()),
        sa.Column("number_value", sa.Float()),
        sa.Column("date_value", sa.DateTime(timezone=True)),
        sa.Column("boolean_value", sa.Boolean()),
        sa.Column("option_id", sa.String(200)),
        sa.Column("user_account_id", sa.String(200)),
        sa.Column("raw_value_json", sa.JSON()),
        sa.UniqueConstraint("issue_id", "jira_field_id", "element_index", name="uq_issue_field_element"),
    )
    for name, columns in [
        ("ix_issue_field_values_issue_id", ["issue_id"]),
        ("ix_issue_field_values_jira_field_id", ["jira_field_id"]),
        ("ix_issue_field_values_value_type", ["value_type"]),
        ("ix_issue_field_values_option_id", ["option_id"]),
        ("ix_issue_field_values_user_account_id", ["user_account_id"]),
        ("ix_field_value_string", ["jira_field_id", "string_value"]),
        ("ix_field_value_number", ["jira_field_id", "number_value"]),
    ]:
        op.create_index(name, "issue_field_values", columns)
    op.create_table(
        "issue_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="SET NULL")),
        sa.Column("child_issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_parent_jira_id", sa.String(100)),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("child_issue_id", "relationship_type", name="uq_child_relationship"),
    )
    op.create_index("ix_issue_relationships_parent_issue_id", "issue_relationships", ["parent_issue_id"])
    op.create_index("ix_issue_relationships_child_issue_id", "issue_relationships", ["child_issue_id"])
    op.create_index("ix_issue_relationships_external_parent_jira_id", "issue_relationships", ["external_parent_jira_id"])
    op.create_table(
        "hierarchy_anomalies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sync_run_id", sa.Integer(), sa.ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anomaly_type", sa.String(40), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_hierarchy_anomalies_sync_run_id", "hierarchy_anomalies", ["sync_run_id"])
    op.create_index("ix_hierarchy_anomalies_issue_id", "hierarchy_anomalies", ["issue_id"])
    op.create_index("ix_hierarchy_anomalies_anomaly_type", "hierarchy_anomalies", ["anomaly_type"])


def downgrade() -> None:
    for table in ["hierarchy_anomalies", "issue_relationships", "issue_field_values", "issues", "sync_runs"]:
        op.drop_table(table)
