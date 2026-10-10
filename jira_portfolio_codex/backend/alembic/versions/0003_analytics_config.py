"""phase 3 analytics configuration

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("metric_type", sa.String(40), nullable=False),
        sa.Column("numerator_filter_json", sa.JSON()),
        sa.Column("denominator_filter_json", sa.JSON()),
        sa.Column("aggregation_json", sa.JSON(), nullable=False),
        sa.Column("field_id", sa.String(200)),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metric_definitions_field_id", "metric_definitions", ["field_id"])
    op.create_table(
        "dashboard_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("layout_json", sa.JSON(), nullable=False),
        sa.Column("filters_json", sa.JSON()),
        sa.Column("owner_id", sa.String(200)),
        sa.Column("shared", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dashboard_configs")
    op.drop_table("metric_definitions")
