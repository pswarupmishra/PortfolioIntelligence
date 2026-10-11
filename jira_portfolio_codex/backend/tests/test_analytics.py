from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analytics import AnalyticsService, FilterValidationError
from app.api import hierarchy_epics
from app.db import Base
from app.models import Issue, IssueFieldValue, JiraField, JiraIssueType, JiraStatus


def analytics_db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    db.add_all(
        [
            JiraStatus(jira_status_id="done", name="Done", category_key="done"),
            JiraStatus(jira_status_id="open", name="Open", category_key="new"),
            JiraStatus(jira_status_id="progress", name="In Progress", category_key="indeterminate"),
            JiraField(jira_field_id="tags", name="Tags", schema_json={"type": "array", "items": "option"}, is_custom=True),
            JiraField(jira_field_id="score", name="Score", schema_json={"type": "number"}, is_custom=True),
            JiraField(jira_field_id="target", name="Target", schema_json={"type": "date"}, is_custom=True),
        ]
    )
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    issues = [
        Issue(
            id=1,
            jira_issue_id="1",
            issue_key="A-1",
            project_jira_id="10732",
            summary="Parent",
            status_jira_id="open",
            due_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
            synced_at=now,
        ),
        Issue(
            id=2,
            jira_issue_id="2",
            issue_key="A-2",
            project_jira_id="10732",
            summary="Done leaf",
            parent_jira_issue_id="1",
            status_jira_id="done",
            synced_at=now,
        ),
        Issue(
            id=3,
            jira_issue_id="3",
            issue_key="A-3",
            project_jira_id="10732",
            summary="Open leaf",
            status_jira_id="progress",
            assignee_account_id="user",
            due_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            baseline_due_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            synced_at=now,
        ),
    ]
    db.add_all(issues)
    db.flush()
    db.add_all(
        [
            IssueFieldValue(
                issue_id=1,
                jira_field_id="tags",
                element_index=0,
                value_type="object",
                option_id="a",
                string_value="Alpha",
                raw_value_json={"id": "a"},
            ),
            IssueFieldValue(
                issue_id=1,
                jira_field_id="tags",
                element_index=1,
                value_type="object",
                option_id="b",
                string_value="Beta",
                raw_value_json={"id": "b"},
            ),
            IssueFieldValue(
                issue_id=2,
                jira_field_id="tags",
                element_index=0,
                value_type="object",
                option_id="a",
                string_value="Alpha",
                raw_value_json={"id": "a"},
            ),
            IssueFieldValue(issue_id=1, jira_field_id="score", element_index=0, value_type="number", number_value=10, raw_value_json=10),
            IssueFieldValue(issue_id=2, jira_field_id="score", element_index=0, value_type="number", number_value=20, raw_value_json=20),
            IssueFieldValue(
                issue_id=2,
                jira_field_id="target",
                element_index=0,
                value_type="date",
                date_value=datetime(2026, 12, 1, tzinfo=timezone.utc),
                raw_value_json="2026-12-01",
            ),
        ]
    )
    db.commit()
    return db


def test_multiselect_grouping_counts_distinct_issues_and_labels_overlap() -> None:
    result = AnalyticsService(analytics_db()).group_by("tags", ["10732"])
    groups = {row["value"]: row["issue_count"] for row in result["groups"]}
    assert groups == {"a": 2, "b": 1, None: 1}
    assert result["non_additive"] is True


def test_numeric_aggregation_excludes_nulls_explicitly() -> None:
    result = AnalyticsService(analytics_db()).numeric_aggregate("score", "avg", ["10732"])
    assert result["value"] == 15
    assert result["distinct_issue_count"] == 2
    assert result["null_issue_count"] == 1
    assert result["null_treatment"] == "excluded"


def test_numeric_and_date_filters_are_typed() -> None:
    service = AnalyticsService(analytics_db())
    assert service.count(["10732"], {"field_id": "score", "operator": "gte", "value": 15}) == 1
    assert service.count(["10732"], {"field_id": "target", "operator": "between", "value": ["2026-11-01", "2026-12-31"]}) == 1
    assert service.count(["10732"], {"field_id": "due_at", "operator": "lte", "value": "2026-10-02"}) == 1


def test_summary_documents_leaf_denominator_and_null_due_dates() -> None:
    result = AnalyticsService(analytics_db()).summary(["10732"])
    metrics = {item["metric_id"]: item for item in result["metrics"]}
    assert metrics["total_work_items"]["value"] == 3
    assert metrics["leaf_completion"]["numerator"] == 1
    assert metrics["leaf_completion"]["denominator"] == 2
    assert result["null_counts"]["due_at"] == 1


def test_card_summary_counts_leaf_tasks_in_progress_and_delayed() -> None:
    result = AnalyticsService(analytics_db()).card_summary(
        ["10732"], {"field_id": "issue_key", "operator": "contains", "value": "A-"}, "status_id"
    )
    assert result["task_count"] == 2
    assert result["in_progress_count"] == 1
    assert result["baseline_delayed_count"] == 1
    assert result["on_track_count"] == 0
    assert result["delayed_count"] == 1
    assert result["no_due_date_count"] == 0
    assert result["next_group_count"] == 3


def test_unknown_fields_and_unsafe_shapes_are_rejected() -> None:
    service = AnalyticsService(analytics_db())
    with pytest.raises(FilterValidationError):
        service.compile_filter({"field_id": "customfield_missing", "operator": "eq", "value": "x"})
    with pytest.raises(FilterValidationError):
        service.compile_filter({"and": [], "sql": "1=1"})


def test_grouped_hierarchy_resolves_matching_descendants_to_epics() -> None:
    db = analytics_db()
    db.add_all(
        [
            JiraIssueType(jira_type_id="epic", name="Epic", hierarchy_level=1),
            JiraIssueType(jira_type_id="story", name="Story", hierarchy_level=0),
        ]
    )
    db.get(Issue, 1).issue_type_jira_id = "epic"  # type: ignore[union-attr]
    db.get(Issue, 2).issue_type_jira_id = "story"  # type: ignore[union-attr]
    db.add(
        IssueFieldValue(
            issue_id=2,
            jira_field_id="tags",
            element_index=2,
            value_type="object",
            option_id="descendant-only",
            string_value="Descendant only",
            raw_value_json={"id": "descendant-only"},
        )
    )
    db.commit()

    result = hierarchy_epics(
        db,
        ["10732"],
        '{"field_id":"tags","operator":"eq","value":"descendant-only"}',
        0,
        50,
    )

    assert result["matching_work_item_count"] == 1
    assert result["total_count"] == 1
    assert result["items"][0]["issue_key"] == "A-1"
