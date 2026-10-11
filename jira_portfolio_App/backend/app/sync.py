import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .jira import JiraClient
from .models import (
    HierarchyAnomaly,
    Issue,
    IssueDateChange,
    IssueFieldValue,
    IssueRelationship,
    JiraProject,
    SyncRun,
)

sync_lock = asyncio.Lock()
SYSTEM_FIELDS = {
    "summary",
    "project",
    "issuetype",
    "status",
    "parent",
    "assignee",
    "reporter",
    "created",
    "updated",
    "duedate",
    "resolutiondate",
}


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), time.min, timezone.utc)
        except ValueError:
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


class SyncBusyError(Exception):
    pass


class SyncService:
    def __init__(self, db: Session, jira: JiraClient) -> None:
        self.db, self.jira = db, jira

    async def run(self, mode: str = "incremental", project_ids: list[str] | None = None) -> SyncRun:
        if sync_lock.locked():
            raise SyncBusyError("Another sync is already running")
        async with sync_lock:
            projects = self._projects(project_ids)
            if not projects:
                raise ValueError("No active Jira projects selected")
            previous = self.db.scalar(select(SyncRun).where(SyncRun.status == "succeeded").order_by(SyncRun.id.desc()))
            watermark = previous.watermark_after if previous else None
            if mode == "incremental" and watermark is None:
                mode = "full"
            run = SyncRun(
                status="running",
                mode=mode,
                projects_json=[p.jira_project_id for p in projects],
                watermark_before=watermark,
            )
            self.db.add(run)
            self.db.commit()
            try:
                jql = self._jql(projects, mode, watermark)
                fetched = [issue async for issue in self.jira.search_issues(jql, ["*all"])]
                now = datetime.now(timezone.utc)
                seen = self._upsert_issues(fetched, run.id, now)
                await self._sync_due_date_history(list(seen))
                if mode == "full":
                    run.missing_count = self._reconcile(run.projects_json, seen)
                self._resolve_relationships(run.id)
                run.anomaly_count = self._detect_anomalies(run.id, run.projects_json)
                run.fetched_count = len(fetched)
                run.upserted_count = len(seen)
                run.watermark_after = (
                    max(
                        (parse_datetime((item.get("fields") or {}).get("updated")) for item in fetched),
                        default=now,
                        key=lambda value: value or datetime.min.replace(tzinfo=timezone.utc),
                    )
                    or now
                )
                run.status, run.finished_at = "succeeded", now
                self.db.commit()
                return run
            except Exception as exc:
                self.db.rollback()
                failed = self.db.get(SyncRun, run.id)
                if failed:
                    failed.status = "failed"
                    failed.finished_at = datetime.now(timezone.utc)
                    failed.error_json = {"type": type(exc).__name__, "message": str(exc)}
                    self.db.commit()
                raise

    async def _sync_due_date_history(self, jira_issue_ids: list[str]) -> None:
        if not jira_issue_ids:
            return
        histories_by_issue: dict[str, list[dict[str, Any]]] = {}
        async for issue_log in self.jira.bulk_changelogs(jira_issue_ids, ["duedate"]):
            issue_id = str(issue_log.get("issueId", ""))
            if issue_id:
                histories_by_issue.setdefault(issue_id, []).extend(issue_log.get("changeHistories") or [])

        for jira_issue_id in jira_issue_ids:
            issue = self.db.scalar(select(Issue).where(Issue.jira_issue_id == jira_issue_id))
            if issue is None:
                continue
            histories = sorted(histories_by_issue.get(jira_issue_id, []), key=lambda row: row.get("created") or "")
            baseline: datetime | None = None
            for history in histories:
                changed_at = parse_datetime(history.get("created"))
                if changed_at is None:
                    continue
                for index, item in enumerate(history.get("items") or []):
                    if item.get("fieldId") != "duedate" and item.get("field") != "Due date":
                        continue
                    from_at = parse_datetime(item.get("fromString"))
                    to_at = parse_datetime(item.get("toString"))
                    baseline = baseline or from_at or to_at
                    changelog_id = str(history.get("id") or f"{changed_at.isoformat()}:{index}")
                    existing = self.db.scalar(
                        select(IssueDateChange).where(
                            IssueDateChange.issue_id == issue.id,
                            IssueDateChange.jira_field_id == "duedate",
                            IssueDateChange.changelog_id == changelog_id,
                        )
                    )
                    if existing is None:
                        self.db.add(
                            IssueDateChange(
                                issue_id=issue.id,
                                jira_field_id="duedate",
                                changelog_id=changelog_id,
                                changed_at=changed_at,
                                author_account_id=(history.get("author") or {}).get("accountId"),
                                from_at=from_at,
                                to_at=to_at,
                            )
                        )
            if issue.baseline_due_at is None:
                issue.baseline_due_at = baseline or issue.due_at

    def _projects(self, project_ids: list[str] | None) -> list[JiraProject]:
        query = select(JiraProject).where(JiraProject.active.is_(True))
        if project_ids:
            query = query.where(JiraProject.jira_project_id.in_(project_ids))
        return list(self.db.scalars(query.order_by(JiraProject.jira_project_id)))

    @staticmethod
    def _jql(projects: list[JiraProject], mode: str, watermark: datetime | None) -> str:
        ids = ",".join(project.jira_project_id for project in projects)
        jql = f"project in ({ids})"
        if mode == "incremental" and watermark:
            if watermark.tzinfo is None:
                watermark = watermark.replace(tzinfo=timezone.utc)
            overlap = watermark.astimezone(timezone.utc) - timedelta(minutes=5)
            jql += f' AND updated >= "{overlap:%Y-%m-%d %H:%M}"'
        return f"{jql} ORDER BY updated ASC, id ASC"

    def _upsert_issues(self, values: list[dict[str, Any]], sync_id: int, now: datetime) -> set[str]:
        seen: set[str] = set()
        for value in values:
            jira_id = str(value["id"])
            fields = value.get("fields") or {}
            project_id = str((fields.get("project") or {}).get("id", ""))
            if not project_id:
                continue
            issue = self.db.scalar(select(Issue).where(Issue.jira_issue_id == jira_id))
            if issue is None:
                issue = Issue(jira_issue_id=jira_id, issue_key=value.get("key", jira_id), project_jira_id=project_id)
                self.db.add(issue)
            issue.issue_key = value.get("key", issue.issue_key)
            issue.project_jira_id = project_id
            issue.issue_type_jira_id = self._nested_id(fields.get("issuetype"))
            issue.status_jira_id = self._nested_id(fields.get("status"))
            issue.parent_jira_issue_id = self._nested_id(fields.get("parent"))
            issue.summary = str(fields.get("summary") or "")
            issue.assignee_account_id = (fields.get("assignee") or {}).get("accountId")
            issue.reporter_account_id = (fields.get("reporter") or {}).get("accountId")
            issue.created_at = parse_datetime(fields.get("created"))
            issue.updated_at = parse_datetime(fields.get("updated"))
            issue.due_at = parse_datetime(fields.get("duedate"))
            issue.resolved_at = parse_datetime(fields.get("resolutiondate"))
            issue.raw_fields_json = fields
            issue.last_seen_sync_id = sync_id
            issue.is_deleted_or_inaccessible = False
            issue.synced_at = now
            self.db.flush()
            self.db.execute(delete(IssueFieldValue).where(IssueFieldValue.issue_id == issue.id))
            for field_id, raw in fields.items():
                if field_id not in SYSTEM_FIELDS:
                    self._store_field_values(issue.id, field_id, raw)
            seen.add(jira_id)
        return seen

    @staticmethod
    def _nested_id(value: Any) -> str | None:
        return str(value["id"]) if isinstance(value, dict) and value.get("id") is not None else None

    def _store_field_values(self, issue_id: int, field_id: str, raw: Any) -> None:
        elements = raw if isinstance(raw, list) else [raw]
        for index, element in enumerate(elements):
            typed = self._typed(element)
            self.db.add(IssueFieldValue(issue_id=issue_id, jira_field_id=field_id, element_index=index, raw_value_json=element, **typed))

    @staticmethod
    def _typed(value: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"value_type": "null"}
        if value is None:
            return result
        if isinstance(value, bool):
            return {"value_type": "boolean", "boolean_value": value}
        if isinstance(value, (int, float)):
            return {"value_type": "number", "number_value": float(value)}
        if isinstance(value, str):
            parsed = parse_datetime(value)
            return {"value_type": "date", "date_value": parsed} if parsed else {"value_type": "string", "string_value": value}
        if isinstance(value, dict):
            label = value.get("value") or value.get("displayName") or value.get("name")
            return {
                "value_type": "object",
                "string_value": str(label) if label is not None else None,
                "option_id": str(value["id"]) if value.get("id") is not None else None,
                "user_account_id": value.get("accountId"),
            }
        return {"value_type": "json", "string_value": str(value)}

    def _reconcile(self, project_ids: list[str], seen: set[str]) -> int:
        query = select(Issue).where(Issue.project_jira_id.in_(project_ids), Issue.is_deleted_or_inaccessible.is_(False))
        missing = 0
        for issue in self.db.scalars(query):
            if issue.jira_issue_id not in seen:
                issue.is_deleted_or_inaccessible = True
                missing += 1
        return missing

    def _resolve_relationships(self, sync_id: int) -> None:
        active = list(self.db.scalars(select(Issue).where(Issue.is_deleted_or_inaccessible.is_(False))))
        by_jira_id = {issue.jira_issue_id: issue for issue in active}
        child_ids = [issue.id for issue in active]
        if child_ids:
            self.db.execute(delete(IssueRelationship).where(IssueRelationship.child_issue_id.in_(child_ids)))
        for child in active:
            if child.parent_jira_issue_id:
                parent = by_jira_id.get(child.parent_jira_issue_id)
                self.db.add(
                    IssueRelationship(
                        parent_issue_id=parent.id if parent else None,
                        child_issue_id=child.id,
                        external_parent_jira_id=None if parent else child.parent_jira_issue_id,
                        relationship_type="parent",
                        is_resolved=parent is not None,
                    )
                )
        self.db.execute(delete(HierarchyAnomaly).where(HierarchyAnomaly.sync_run_id == sync_id))

    def _detect_anomalies(self, sync_id: int, project_ids: list[str]) -> int:
        issues = list(
            self.db.scalars(select(Issue).where(Issue.project_jira_id.in_(project_ids), Issue.is_deleted_or_inaccessible.is_(False)))
        )
        by_jira_id = {issue.jira_issue_id: issue for issue in issues}
        anomalies: dict[tuple[int, str], dict[str, Any]] = {}
        for issue in issues:
            parent_id = issue.parent_jira_issue_id
            if parent_id and parent_id not in by_jira_id:
                anomalies[(issue.id, "missing_parent")] = {"parent_jira_issue_id": parent_id}
            visited: set[str] = set()
            current = issue
            while current.parent_jira_issue_id and current.parent_jira_issue_id in by_jira_id:
                if current.jira_issue_id in visited:
                    anomalies[(issue.id, "cycle")] = {"at_jira_issue_id": current.jira_issue_id}
                    break
                visited.add(current.jira_issue_id)
                current = by_jira_id[current.parent_jira_issue_id]
        for (issue_id, anomaly_type), details in anomalies.items():
            self.db.add(HierarchyAnomaly(sync_run_id=sync_id, issue_id=issue_id, anomaly_type=anomaly_type, details_json=details))
        return len(anomalies)


def sync_version(db: Session) -> int:
    return db.scalar(select(func.max(SyncRun.id)).where(SyncRun.status == "succeeded")) or 0
