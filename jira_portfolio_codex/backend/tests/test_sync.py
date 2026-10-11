from collections.abc import AsyncIterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import HierarchyAnomaly, Issue, IssueFieldValue, IssueRelationship, JiraProject
from app.sync import SyncService


def issue(
    issue_id: str,
    key: str,
    parent: str | None = None,
    *,
    updated: str = "2026-10-10T10:00:00Z",
    custom: object = None,
    due_date: str | None = None,
) -> dict:
    fields = {
        "project": {"id": "10732"},
        "summary": key,
        "issuetype": {"id": "1"},
        "status": {"id": "2"},
        "updated": updated,
        "created": "2026-01-01T00:00:00Z",
        "customfield_dynamic": custom,
        "duedate": due_date,
    }
    if parent:
        fields["parent"] = {"id": parent}
    return {"id": issue_id, "key": key, "fields": fields}


class StubJira:
    def __init__(self, pages: list[list[dict]], changelogs: list[dict] | None = None) -> None:
        self.pages = pages
        self.changelogs = changelogs or []
        self.jqls: list[str] = []

    async def search_issues(self, jql: str, fields: list[str], page_size: int = 100) -> AsyncIterator[dict]:
        self.jqls.append(jql)
        assert fields == ["*all"]
        for page in self.pages:
            for value in page:
                yield value

    async def bulk_changelogs(self, issue_ids_or_keys: list[str], field_ids: list[str]) -> AsyncIterator[dict]:
        assert field_ids == ["duedate"]
        for value in self.changelogs:
            yield value


def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    db.add(JiraProject(jira_project_id="10732", key="SDHI", name="Salem", active=True))
    db.commit()
    return db


async def test_full_sync_preserves_real_hierarchy_and_typed_values() -> None:
    db = session()
    jira = StubJira(
        [
            [issue("1", "SDHI-1", custom={"id": "green", "value": "Green"}), issue("2", "SDHI-2", "1")],
            [issue("3", "SDHI-3", "2"), issue("4", "SDHI-4", "3"), issue("5", "SDHI-5")],
        ]
    )
    run = await SyncService(db, jira).run("full", ["10732"])  # type: ignore[arg-type]
    assert run.fetched_count == 5
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "4")).parent_jira_issue_id == "3"
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "5")).parent_jira_issue_id is None
    typed = db.scalar(
        select(IssueFieldValue).where(IssueFieldValue.jira_field_id == "customfield_dynamic", IssueFieldValue.option_id == "green")
    )
    assert typed.option_id == "green" and typed.string_value == "Green"
    assert len(list(db.scalars(select(IssueRelationship)))) == 3


async def test_incremental_updates_parent_without_tombstoning_unseen() -> None:
    db = session()
    await SyncService(db, StubJira([[issue("1", "SDHI-1"), issue("2", "SDHI-2", "1")]])).run("full", ["10732"])  # type: ignore[arg-type]
    jira = StubJira([[issue("2", "SDHI-2", None, updated="2026-10-10T11:00:00Z")]])
    run = await SyncService(db, jira).run("incremental", ["10732"])  # type: ignore[arg-type]
    assert "updated >=" in jira.jqls[0]
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "2")).parent_jira_issue_id is None
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "1")).is_deleted_or_inaccessible is False
    assert run.missing_count == 0


async def test_full_reconciliation_tombstones_missing_issue() -> None:
    db = session()
    await SyncService(db, StubJira([[issue("1", "SDHI-1"), issue("2", "SDHI-2")]])).run("full", ["10732"])  # type: ignore[arg-type]
    run = await SyncService(db, StubJira([[issue("1", "SDHI-1")]])).run("full", ["10732"])  # type: ignore[arg-type]
    assert run.missing_count == 1
    assert db.scalar(select(Issue).where(Issue.jira_issue_id == "2")).is_deleted_or_inaccessible is True


async def test_missing_parents_and_cycles_are_flagged() -> None:
    db = session()
    jira = StubJira([[issue("1", "SDHI-1", "2"), issue("2", "SDHI-2", "1"), issue("3", "SDHI-3", "outside")]])
    run = await SyncService(db, jira).run("full", ["10732"])  # type: ignore[arg-type]
    anomalies = list(db.scalars(select(HierarchyAnomaly).where(HierarchyAnomaly.sync_run_id == run.id)))
    assert {item.anomaly_type for item in anomalies} == {"cycle", "missing_parent"}
    assert run.anomaly_count == 3


async def test_due_date_changelog_preserves_first_assigned_baseline() -> None:
    db = session()
    jira = StubJira(
        [[issue("1", "SDHI-1", due_date="2026-12-15")]],
        [
            {
                "issueId": "1",
                "changeHistories": [
                    {
                        "id": "101",
                        "created": "2026-01-02T10:00:00Z",
                        "author": {"accountId": "pmo-user"},
                        "items": [{"fieldId": "duedate", "field": "Due date", "fromString": None, "toString": "2026-10-01"}],
                    },
                    {
                        "id": "102",
                        "created": "2026-09-30T10:00:00Z",
                        "author": {"accountId": "pmo-user"},
                        "items": [
                            {"fieldId": "duedate", "field": "Due date", "fromString": "2026-10-01", "toString": "2026-12-15"}
                        ],
                    },
                ],
            }
        ],
    )
    await SyncService(db, jira).run("full", ["10732"])  # type: ignore[arg-type]
    saved = db.scalar(select(Issue).where(Issue.jira_issue_id == "1"))
    assert saved is not None
    assert saved.baseline_due_at.isoformat().startswith("2026-10-01")  # type: ignore[union-attr]
    assert saved.due_at.isoformat().startswith("2026-12-15")  # type: ignore[union-attr]
