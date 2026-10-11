from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import (
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
)
from app.db import Base
from app.main import app
from app.models import Issue, IssueFieldValue, JiraField, JiraProject, TraceabilityConfig
from app.schemas import GridConfigIn, SprintViewConfigIn, TraceabilityConfigIn


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
    db.add(IssueFieldValue(issue_id=issue.id, jira_field_id="labels", element_index=0, value_type="string", string_value="delivery", raw_value_json="delivery"))
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
