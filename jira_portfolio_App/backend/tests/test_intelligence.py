from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Issue, JiraProject, JiraStatus
from app import intelligence


def test_snapshot_is_idempotent_and_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_DB_PATH", str(tmp_path / "history.db"))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(JiraProject(jira_project_id="p1", key="TEST", name="Test", active=True))
        session.add(JiraStatus(jira_status_id="s1", name="Done", category_key="done"))
        session.add(Issue(jira_issue_id="i1", issue_key="TEST-1", project_jira_id="p1", status_jira_id="s1"))
        session.commit()
        assert intelligence.capture(session, 1, ["p1"]) == 1
        assert intelligence.capture(session, 1, ["p1"]) == 0
    result = intelligence.report("p1")
    assert result["latest"]["total"] == 1
    assert result["latest"]["done"] == 1
    assert result["latest"]["completion_pct"] == 100
    assert (tmp_path / "history.db").exists()
