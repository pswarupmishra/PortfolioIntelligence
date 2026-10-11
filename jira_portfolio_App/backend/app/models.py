from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JiraConnection(Base):
    __tablename__ = "jira_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Jira Cloud")
    base_url: Mapped[str] = mapped_column(String(500), unique=True)
    auth_method: Mapped[str] = mapped_column(String(30), default="basic_api_token")
    credential_reference: Mapped[str] = mapped_column(String(200), default="environment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JiraProject(Base):
    __tablename__ = "jira_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_project_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectPlan(Base):
    __tablename__ = "project_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id", ondelete="CASCADE"), unique=True, index=True)
    start_date: Mapped[date] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectPlanBaseline(Base):
    __tablename__ = "project_plan_baselines"
    __table_args__ = (UniqueConstraint("project_plan_id", "version", name="uq_project_plan_baseline_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_plan_id: Mapped[int] = mapped_column(ForeignKey("project_plans.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    end_date: Mapped[date] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JiraField(Base):
    __tablename__ = "jira_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_field_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    contexts: Mapped[list["JiraFieldContext"]] = relationship(cascade="all, delete-orphan")


class JiraFieldContext(Base):
    __tablename__ = "jira_field_contexts"
    __table_args__ = (UniqueConstraint("jira_field_id", "context_id", name="uq_field_context"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_field_id: Mapped[str] = mapped_column(ForeignKey("jira_fields.jira_field_id", ondelete="CASCADE"), index=True)
    context_id: Mapped[str] = mapped_column(String(200))
    project_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    issue_type_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    availability: Mapped[str] = mapped_column(String(40), default="available")
    message: Mapped[str | None] = mapped_column(String(1000))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JiraIssueType(Base):
    __tablename__ = "jira_issue_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_type_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    hierarchy_level: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JiraStatus(Base):
    __tablename__ = "jira_statuses"
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_status_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    category_key: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetadataRefresh(Base):
    __tablename__ = "metadata_refreshes"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), index=True)
    counts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    projects_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    upserted_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    watermark_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    watermark_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    jira_issue_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    issue_key: Mapped[str] = mapped_column(String(100), index=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id"), index=True)
    issue_type_jira_id: Mapped[str | None] = mapped_column(String(100), index=True)
    status_jira_id: Mapped[str | None] = mapped_column(String(100), index=True)
    parent_jira_issue_id: Mapped[str | None] = mapped_column(String(100), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    assignee_account_id: Mapped[str | None] = mapped_column(String(200))
    reporter_account_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    baseline_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_fields_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_sync_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    is_deleted_or_inaccessible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    field_values: Mapped[list["IssueFieldValue"]] = relationship(cascade="all, delete-orphan")


class IssueDateChange(Base):
    __tablename__ = "issue_date_changes"
    __table_args__ = (UniqueConstraint("issue_id", "jira_field_id", "changelog_id", name="uq_issue_date_changelog"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    jira_field_id: Mapped[str] = mapped_column(String(200), index=True)
    changelog_id: Mapped[str] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    author_account_id: Mapped[str | None] = mapped_column(String(200))
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IssueFieldValue(Base):
    __tablename__ = "issue_field_values"
    __table_args__ = (UniqueConstraint("issue_id", "jira_field_id", "element_index", name="uq_issue_field_element"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    jira_field_id: Mapped[str] = mapped_column(String(200), index=True)
    element_index: Mapped[int] = mapped_column(Integer, default=0)
    value_type: Mapped[str] = mapped_column(String(30), index=True)
    string_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(Float)
    date_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    option_id: Mapped[str | None] = mapped_column(String(200), index=True)
    user_account_id: Mapped[str | None] = mapped_column(String(200), index=True)
    raw_value_json: Mapped[Any] = mapped_column(JSON)


class IssueRelationship(Base):
    __tablename__ = "issue_relationships"
    __table_args__ = (UniqueConstraint("child_issue_id", "relationship_type", name="uq_child_relationship"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id", ondelete="SET NULL"), index=True)
    child_issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    external_parent_jira_id: Mapped[str | None] = mapped_column(String(100), index=True)
    relationship_type: Mapped[str] = mapped_column(String(30), default="parent")
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class HierarchyAnomaly(Base):
    __tablename__ = "hierarchy_anomalies"
    id: Mapped[int] = mapped_column(primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(40), index=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    metric_type: Mapped[str] = mapped_column(String(40))
    numerator_filter_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    denominator_filter_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    aggregation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    field_id: Mapped[str | None] = mapped_column(String(200), index=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DashboardConfig(Base):
    __tablename__ = "dashboard_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    layout_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    owner_id: Mapped[str | None] = mapped_column(String(200))
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(30), default="user", index=True)
    screen_permissions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AppSession(Base):
    __tablename__ = "app_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TraceabilityConfig(Base):
    __tablename__ = "traceability_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id", ondelete="CASCADE"), unique=True, index=True)
    grouping_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    level_captions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GridConfig(Base):
    __tablename__ = "grid_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id", ondelete="CASCADE"), unique=True, index=True)
    optional_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SprintGridConfig(Base):
    __tablename__ = "sprint_grid_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id", ondelete="CASCADE"), unique=True, index=True)
    optional_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SprintViewConfig(Base):
    __tablename__ = "sprint_view_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_jira_id: Mapped[str] = mapped_column(ForeignKey("jira_projects.jira_project_id", ondelete="CASCADE"), unique=True, index=True)
    grouping_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    level_captions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


Index("ix_field_context_scope", JiraFieldContext.jira_field_id, JiraFieldContext.context_id)
Index("ix_issues_project_parent", Issue.project_jira_id, Issue.parent_jira_issue_id)
Index("ix_field_value_string", IssueFieldValue.jira_field_id, IssueFieldValue.string_value)
Index("ix_field_value_number", IssueFieldValue.jira_field_id, IssueFieldValue.number_value)
