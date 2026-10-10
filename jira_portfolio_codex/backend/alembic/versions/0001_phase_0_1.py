"""phase 0 and 1 metadata catalog

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jira_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False, unique=True),
        sa.Column("auth_method", sa.String(30), nullable=False),
        sa.Column("credential_reference", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jira_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_project_id", sa.String(100), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jira_project_id"),
    )
    op.create_index("ix_jira_projects_jira_project_id", "jira_projects", ["jira_project_id"], unique=True)
    op.create_index("ix_jira_projects_key", "jira_projects", ["key"])
    op.create_index("ix_jira_projects_active", "jira_projects", ["active"])
    op.create_table(
        "jira_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_field_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False),
        sa.Column("searchable", sa.Boolean(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jira_field_id"),
    )
    op.create_index("ix_jira_fields_jira_field_id", "jira_fields", ["jira_field_id"], unique=True)
    op.create_index("ix_jira_fields_name", "jira_fields", ["name"])
    op.create_index("ix_jira_fields_selected", "jira_fields", ["selected"])
    op.create_table(
        "jira_field_contexts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_field_id", sa.String(200), sa.ForeignKey("jira_fields.jira_field_id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_id", sa.String(200), nullable=False),
        sa.Column("project_ids_json", sa.JSON(), nullable=False),
        sa.Column("issue_type_ids_json", sa.JSON(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("availability", sa.String(40), nullable=False),
        sa.Column("message", sa.String(1000)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jira_field_id", "context_id", name="uq_field_context"),
    )
    op.create_index("ix_jira_field_contexts_jira_field_id", "jira_field_contexts", ["jira_field_id"])
    op.create_index("ix_field_context_scope", "jira_field_contexts", ["jira_field_id", "context_id"])
    op.create_table(
        "jira_issue_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_type_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("hierarchy_level", sa.Integer()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jira_type_id"),
    )
    op.create_index("ix_jira_issue_types_jira_type_id", "jira_issue_types", ["jira_type_id"], unique=True)
    op.create_table(
        "jira_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_status_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("category_key", sa.String(100)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jira_status_id"),
    )
    op.create_index("ix_jira_statuses_jira_status_id", "jira_statuses", ["jira_status_id"], unique=True)
    op.create_table(
        "metadata_refreshes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("counts_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON()),
    )
    op.create_index("ix_metadata_refreshes_status", "metadata_refreshes", ["status"])


def downgrade() -> None:
    tables = [
        "metadata_refreshes",
        "jira_statuses",
        "jira_issue_types",
        "jira_field_contexts",
        "jira_fields",
        "jira_projects",
        "jira_connections",
    ]
    for table in tables:
        op.drop_table(table)
