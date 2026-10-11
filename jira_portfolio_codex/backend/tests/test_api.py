from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import get_traceability_config, save_traceability_config
from app.db import Base
from app.main import app
from app.models import JiraField, JiraProject
from app.schemas import TraceabilityConfigIn


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
    saved = save_traceability_config("10732", TraceabilityConfigIn(grouping_fields=["customfield_phase", "status_id"]), db)

    assert saved["persisted"] is True
    assert get_traceability_config("10732", db)["grouping_fields"] == ["customfield_phase", "status_id"]


def test_traceability_configuration_has_no_fixed_level_limit() -> None:
    fields = ["status_id", "issue_type_id", "assignee", "labels", "customfield_phase", "status_id"]
    assert TraceabilityConfigIn(grouping_fields=fields).grouping_fields == fields
