from fastapi.testclient import TestClient
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api import (
    fields as list_fields,
)
from app.api import (
    delete_project_data,
    get_grid_config,
    get_sprint_grid_config,
    get_sprint_view_config,
    get_traceability_config,
    grafana_traceability,
    grafana_wbs,
    save_grid_config,
    save_sprint_grid_config,
    save_sprint_view_config,
    save_traceability_config,
    select_fields,
)
from app.db import Base
from app.main import app
from app.models import GridConfig, Issue, IssueDateChange, IssueFieldValue, JiraField, JiraFieldContext, JiraProject, SprintGridConfig, SprintViewConfig, TraceabilityConfig
from app.schemas import FieldBulkSelection, GridConfigIn, SprintViewConfigIn, TraceabilityConfigIn


def test_live_health() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_route_requires_role() -> None:
    response = TestClient(app).post("/api/v1/jira/test-connection")
    assert response.status_code == 403


def test_traceability_configuration_is_persisted_per_project() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            JiraProject(jira_project_id="10732", key="SDHI", name="Salem"),
            JiraField(jira_field_id="labels", name="Labels", schema_json={"type": "array"}, is_custom=False),
            JiraField(jira_field_id="customfield_phase", name="Phase", schema_json={"type": "option"}, is_custom=True),
        ]
    )
    db.commit()

    default = get_traceability_config("10732", db)
    assert default["grouping_fields"] == ["labels", "status_id", "issue_type_id"]
    saved = save_traceability_config(
        "10732", TraceabilityConfigIn(grouping_fields=["customfield_phase", "status_id"], level_captions=["Delivery phase", "Workflow"]), db
    )

    assert saved["persisted"] is True
    assert saved["level_captions"] == ["Delivery phase", "Workflow"]
    assert get_traceability_config("10732", db)["grouping_fields"] == ["customfield_phase", "status_id"]


def test_traceability_configuration_has_no_fixed_level_limit() -> None:
    fields = ["status_id", "issue_type_id", "assignee", "labels", "customfield_phase", "status_id"]
    assert TraceabilityConfigIn(grouping_fields=fields).grouping_fields == fields


def test_bulk_field_selection_updates_only_requested_catalog_fields() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            JiraField(jira_field_id="labels", name="Labels", schema_json={"type": "array"}, is_custom=False),
            JiraField(jira_field_id="assignee", name="Assignee", schema_json={"type": "user"}, is_custom=False),
            JiraField(jira_field_id="summary", name="Summary", schema_json={"type": "string"}, is_custom=False),
        ]
    )
    db.commit()

    result = select_fields(FieldBulkSelection(field_ids=["labels", "assignee"], selected=True), db)

    assert result == {"updated_count": 2, "selected": True}
    assert db.scalar(select(JiraField).where(JiraField.jira_field_id == "labels")).selected is True
    assert db.scalar(select(JiraField).where(JiraField.jira_field_id == "summary")).selected is False


def test_project_data_deletion_is_scoped_and_removes_project_metadata() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            JiraProject(jira_project_id="10732", key="SDHI", name="Salem"),
            JiraProject(jira_project_id="10467", key="QA", name="Quality"),
            JiraField(jira_field_id="customfield_phase", name="Phase", schema_json={"type": "option"}, is_custom=True),
        ]
    )
    db.flush()
    removed_issue = Issue(jira_issue_id="1", issue_key="SDHI-1", project_jira_id="10732", summary="Remove")
    retained_issue = Issue(jira_issue_id="2", issue_key="QA-1", project_jira_id="10467", summary="Keep")
    db.add_all([removed_issue, retained_issue])
    db.flush()
    db.add(IssueFieldValue(issue_id=removed_issue.id, jira_field_id="customfield_phase", element_index=0, value_type="string", string_value="One", raw_value_json="One"))
    db.add(IssueDateChange(issue_id=removed_issue.id, jira_field_id="duedate", changelog_id="1", changed_at=datetime.now(timezone.utc)))
    db.add_all(
        [
            TraceabilityConfig(project_jira_id="10732", grouping_fields_json=["customfield_phase"]),
            GridConfig(project_jira_id="10732", optional_fields_json=["customfield_phase"]),
            SprintViewConfig(project_jira_id="10732", grouping_fields_json=["status_id"]),
            SprintGridConfig(project_jira_id="10732", optional_fields_json=[]),
            JiraFieldContext(jira_field_id="customfield_phase", context_id="sdhi", project_ids_json=["10732"], issue_type_ids_json=[], availability="available"),
            JiraFieldContext(jira_field_id="customfield_phase", context_id="shared", project_ids_json=["10732", "10467"], issue_type_ids_json=[], availability="available"),
        ]
    )
    db.commit()

    result = delete_project_data("10732", db, confirm="10732")

    assert result["deleted"]["issues"] == 1
    assert db.scalar(select(JiraProject).where(JiraProject.jira_project_id == "10732")) is None
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "1")) is None
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "2")) is not None
    assert db.scalar(select(func.count()).select_from(TraceabilityConfig)) == 0
    assert db.scalar(select(JiraFieldContext).where(JiraFieldContext.context_id == "sdhi")) is None
    shared = db.scalar(select(JiraFieldContext).where(JiraFieldContext.context_id == "shared"))
    assert shared is not None and shared.project_ids_json == ["10467"]


def test_project_field_catalog_excludes_permission_limited_custom_fields() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(JiraProject(jira_project_id="10965", key="ATHP", name="Agile Template Hardware Project"))
    db.add_all(
        [
            JiraField(jira_field_id="summary", name="Summary", schema_json={"type": "string"}, is_custom=False),
            JiraField(jira_field_id="customfield_10815", name="Bluemingo Rule", schema_json={"type": "string"}, is_custom=True),
        ]
    )
    db.add(
        JiraFieldContext(
            jira_field_id="customfield_10815",
            context_id="permission-limited",
            project_ids_json=[],
            issue_type_ids_json=[],
            availability="not_applicable",
            message="This Jira field does not expose contexts",
        )
    )
    db.commit()

    result = list_fields(db, project_id="10965", limit=500, cursor=0)

    assert [field.jira_field_id for field in result.items] == ["summary"]


def test_grafana_traceability_exports_configured_node_graph_frames() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(JiraProject(jira_project_id="10732", key="SDHI", name="Salem"))
    db.add(JiraField(jira_field_id="labels", name="Labels", schema_json={"type": "array"}, is_custom=False))
    db.add(TraceabilityConfig(project_jira_id="10732", grouping_fields_json=["labels"], level_captions_json=["Work group"]))
    issue = Issue(jira_issue_id="1", issue_key="SDHI-1", project_jira_id="10732", summary="Example")
    db.add(issue)
    db.flush()
    db.add(
        IssueFieldValue(
            issue_id=issue.id,
            jira_field_id="labels",
            element_index=0,
            value_type="string",
            string_value="delivery",
            raw_value_json="delivery",
        )
    )
    db.commit()

    result = grafana_traceability("10732", db)

    assert result["project"] == {"id": "10732", "key": "SDHI", "name": "Salem"}
    assert result["view"] == "traceability_cards"
    assert result["configuration"]["levels"] == [{"field_id": "labels", "caption": "Work group"}]
    assert result["summary"] == {"issue_count": 1, "level_count": 1, "card_count": 1, "node_count": 1, "edge_count": 0}
    assert result["nodes"][0]["title"] == "delivery"
    assert result["nodes"][0]["subTitle"] == "Work group"
    assert result["traceability"]["cards"][0]["metrics"]["task_count"] == 1
    assert result["traceability"]["cards"][0]["work_items"][0]["issue_key"] == "SDHI-1"
    assert result["grafana"]["recommended_visualizations"] == ["Node graph", "Table", "Stat"]

    wbs = grafana_wbs("10732", db)
    assert wbs["view"] == "wbs_flow"
    assert wbs["configuration"]["levels"] == [{"field_id": "labels", "caption": "Work group"}]
    assert wbs["summary"] == {"issue_count": 1, "node_count": 1, "edge_count": 0}
    assert wbs["nodes"][0]["title"] == "delivery"


def test_grid_configuration_is_project_specific_and_ordered() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(JiraProject(jira_project_id="10732", key="SDHI", name="Salem"))
    db.add_all(
        [
            JiraField(jira_field_id="labels", name="Labels", schema_json={"type": "array"}, is_custom=False),
            JiraField(jira_field_id="assignee", name="Assignee", schema_json={"type": "user"}, is_custom=False),
        ]
    )
    db.add(
        Issue(
            jira_issue_id="1",
            issue_key="SDHI-1",
            project_jira_id="10732",
            summary="Example",
            raw_fields_json={"assignee": {"displayName": "User"}, "labels": ["delivery"]},
        )
    )
    db.commit()

    saved = save_grid_config("10732", GridConfigIn(optional_fields=["assignee", "labels"]), db)

    assert [field["field_id"] for field in saved["optional_fields"]] == ["assignee", "labels"]
    assert get_grid_config("10732", db)["mandatory_columns"] == [
        "key", "summary", "issue_type", "baseline_due", "revised_due", "status"
    ]
    sprint_saved = save_sprint_grid_config("10732", GridConfigIn(optional_fields=["labels"]), db)
    assert [field["field_id"] for field in sprint_saved["optional_fields"]] == ["labels"]
    assert [field["field_id"] for field in get_grid_config("10732", db)["optional_fields"]] == ["assignee", "labels"]
    assert [field["field_id"] for field in get_sprint_grid_config("10732", db)["optional_fields"]] == ["labels"]


def test_sprint_view_configuration_uses_applicable_project_fields_and_captions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(JiraProject(jira_project_id="10732", key="SDHI", name="Salem"))
    db.add(JiraField(jira_field_id="customfield_sprint", name="Sprint", schema_json={"type": "array"}, is_custom=True))
    db.add(
        Issue(
            jira_issue_id="1",
            issue_key="SDHI-1",
            project_jira_id="10732",
            summary="Example",
            raw_fields_json={"customfield_sprint": [{"name": "Sprint 1"}]},
        )
    )
    db.commit()

    saved = save_sprint_view_config(
        "10732",
        SprintViewConfigIn(
            grouping_fields=["customfield_sprint", "status_id"], level_captions=["Delivery sprint", "Workflow"]
        ),
        db,
    )

    assert saved["level_captions"] == ["Delivery sprint", "Workflow"]
    assert get_sprint_view_config("10732", db)["grouping_fields"] == ["customfield_sprint", "status_id"]
