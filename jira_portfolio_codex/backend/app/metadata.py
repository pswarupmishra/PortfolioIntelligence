import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .jira import JiraClient, JiraError
from .models import (
    JiraField,
    JiraFieldContext,
    JiraIssueType,
    JiraProject,
    JiraStatus,
    MetadataRefresh,
)


class MetadataService:
    def __init__(self, db: Session, jira: JiraClient) -> None:
        self.db, self.jira = db, jira

    async def refresh(self) -> MetadataRefresh:
        run = MetadataRefresh(status="running")
        self.db.add(run)
        self.db.commit()
        warnings: list[dict[str, Any]] = []
        try:
            projects, fields, issue_types, statuses = await asyncio.gather(
                self.jira.projects(), self.jira.fields(), self.jira.issue_types(), self.jira.statuses()
            )
            now = datetime.now(timezone.utc)
            self._upsert_projects(projects, now)
            custom_fields = self._upsert_fields(fields, now)
            self._upsert_issue_types(issue_types, now)
            self._upsert_statuses(statuses, now)
            semaphore = asyncio.Semaphore(4)

            async def discover(field: dict[str, Any]) -> None:
                async with semaphore:
                    await self._refresh_contexts(str(field["id"]), warnings, now)

            await asyncio.gather(*(discover(field) for field in custom_fields))
            run.status, run.finished_at = "succeeded", now
            run.counts_json = {"projects": len(projects), "fields": len(fields), "issue_types": len(issue_types), "statuses": len(statuses)}
            run.warnings_json = warnings
            self.db.commit()
            return run
        except Exception as exc:
            self.db.rollback()
            failed_run = self.db.get(MetadataRefresh, run.id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.finished_at = datetime.now(timezone.utc)
                failed_run.error_json = {"type": type(exc).__name__, "message": str(exc)}
                self.db.commit()
            raise

    def _upsert_projects(self, values: list[dict[str, Any]], now: datetime) -> None:
        for value in values:
            row = self.db.scalar(select(JiraProject).where(JiraProject.jira_project_id == str(value["id"])))
            if row is None:
                row = JiraProject(jira_project_id=str(value["id"]), key=value["key"], name=value["name"])
                self.db.add(row)
            row.key, row.name, row.metadata_json, row.updated_at = value["key"], value["name"], value, now

    def _upsert_fields(self, values: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
        custom = []
        for value in values:
            field_id = str(value["id"])
            row = self.db.scalar(select(JiraField).where(JiraField.jira_field_id == field_id))
            if row is None:
                row = JiraField(jira_field_id=field_id, name=value["name"])
                self.db.add(row)
            row.name = value["name"]
            row.schema_json = value.get("schema") or {}
            row.is_custom = bool(value.get("custom", False))
            row.searchable = bool(value.get("searchable", True))
            row.last_seen_at = now
            if row.is_custom:
                custom.append(value)
        self.db.flush()
        return custom

    def _upsert_issue_types(self, values: list[dict[str, Any]], now: datetime) -> None:
        for value in values:
            key = str(value["id"])
            row = self.db.scalar(select(JiraIssueType).where(JiraIssueType.jira_type_id == key))
            if row is None:
                row = JiraIssueType(jira_type_id=key, name=value["name"])
                self.db.add(row)
            row.name, row.hierarchy_level = value["name"], value.get("hierarchyLevel")
            row.metadata_json, row.last_seen_at = value, now

    def _upsert_statuses(self, values: list[dict[str, Any]], now: datetime) -> None:
        for value in values:
            key = str(value["id"])
            row = self.db.scalar(select(JiraStatus).where(JiraStatus.jira_status_id == key))
            if row is None:
                row = JiraStatus(jira_status_id=key, name=value["name"])
                self.db.add(row)
            row.name = value["name"]
            row.category_key = (value.get("statusCategory") or {}).get("key")
            row.metadata_json, row.last_seen_at = value, now

    async def _refresh_contexts(self, field_id: str, warnings: list[dict[str, Any]], now: datetime) -> None:
        try:
            contexts = await self.jira.field_contexts(field_id)
        except JiraError as exc:
            if exc.status_code == 403:
                self._limited_context(
                    field_id,
                    "contexts_forbidden",
                    "Jira did not permit context discovery",
                    now,
                )
                warnings.append({"field_id": field_id, "code": "contexts_forbidden"})
                return
            if exc.details.get("jira_status") == 404:
                self._limited_context(
                    field_id,
                    "not_applicable",
                    "This Jira field does not expose contexts",
                    now,
                )
                warnings.append({"field_id": field_id, "code": "contexts_not_applicable"})
                return
            raise
        for value in contexts:
            context_id = str(value["id"])
            availability, message, options = "available", None, []
            try:
                options = await self.jira.context_options(field_id, context_id)
            except JiraError as exc:
                if exc.status_code == 403:
                    availability, message = "options_forbidden", "Jira did not permit option discovery"
                    warnings.append({"field_id": field_id, "context_id": context_id, "code": availability})
                elif exc.details.get("jira_status") in (400, 404):
                    availability, message = "not_applicable", "This context does not expose options"
                else:
                    raise
            row = self.db.scalar(
                select(JiraFieldContext).where(JiraFieldContext.jira_field_id == field_id, JiraFieldContext.context_id == context_id)
            )
            if row is None:
                row = JiraFieldContext(jira_field_id=field_id, context_id=context_id)
                self.db.add(row)
            row.project_ids_json = [str(x) for x in value.get("projectIds", [])]
            row.issue_type_ids_json = [str(x) for x in value.get("issueTypeIds", [])]
            row.options_json, row.availability, row.message, row.fetched_at = options, availability, message, now

    def _limited_context(self, field_id: str, code: str, message: str, now: datetime) -> None:
        row = self.db.scalar(
            select(JiraFieldContext).where(JiraFieldContext.jira_field_id == field_id, JiraFieldContext.context_id == "permission-limited")
        )
        if row is None:
            row = JiraFieldContext(jira_field_id=field_id, context_id="permission-limited")
            self.db.add(row)
        row.availability, row.message, row.fetched_at = code, message, now
