from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ListEnvelope(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    total_count: int | None = None
    sync_version: int = 0


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jira_project_id: str
    key: str
    name: str
    active: bool
    updated_at: datetime


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    jira_field_id: str
    name: str
    schema_data: dict[str, Any] = Field(alias="schema_json")
    is_custom: bool
    searchable: bool
    selected: bool
    last_seen_at: datetime


class IssueTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jira_type_id: str
    name: str
    hierarchy_level: int | None
    metadata_json: dict[str, Any]


class StatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jira_status_id: str
    name: str
    category_key: str | None
    metadata_json: dict[str, Any]


class SelectionUpdate(BaseModel):
    selected: bool


class FieldBulkSelection(BaseModel):
    field_ids: list[str] = Field(min_length=1, max_length=500)
    selected: bool


class SyncRequest(BaseModel):
    mode: str = "incremental"
    project_ids: list[str] | None = None


class GroupByRequest(BaseModel):
    project_ids: list[str] | None = None
    filters: dict[str, Any] | None = None
    field_id: str
    aggregation: str = "count"


class CardSummaryRequest(BaseModel):
    project_ids: list[str] | None = None
    filters: dict[str, Any] | None = None
    field_id: str
    next_field_id: str | None = None


class MetricConfigIn(BaseModel):
    name: str
    metric_type: str = "ratio"
    numerator_filter: dict[str, Any] | None = None
    denominator_filter: dict[str, Any] | None = None
    aggregation: dict[str, Any] = {}
    field_id: str | None = None
    scope: dict[str, Any] = {}


class DashboardConfigIn(BaseModel):
    name: str
    description: str = ""
    scope: dict[str, Any] = {}
    layout: dict[str, Any] = {}
    filters: dict[str, Any] | None = None
    shared: bool = False


class TraceabilityConfigIn(BaseModel):
    grouping_fields: list[str] = Field(min_length=1)
    level_captions: list[str] = Field(default_factory=list)


class GridConfigIn(BaseModel):
    optional_fields: list[str] = Field(default_factory=list)


class SprintViewConfigIn(BaseModel):
    grouping_fields: list[str] = Field(min_length=1)
    level_captions: list[str] = Field(default_factory=list)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    role: str = "user"
    screen_permissions: list[str] = Field(default_factory=list)
    active: bool = True
