from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import (
    get_grid_config,
    get_sprint_view_config,
    get_traceability_config,
    save_grid_config,
    save_sprint_view_config,
    save_traceability_config,
)
from app.db import Base
from app.main import app
from app.models import Issue, JiraField, JiraProject
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
