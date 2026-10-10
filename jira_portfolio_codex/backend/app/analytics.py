from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, and_, cast, distinct, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from .models import Issue, IssueFieldValue, JiraField, JiraStatus
from .sync import parse_datetime, sync_version

CORE_FIELDS: dict[str, Any] = {
    "issue_key": Issue.issue_key,
    "project_id": Issue.project_jira_id,
    "issue_type_id": Issue.issue_type_jira_id,
    "status_id": Issue.status_jira_id,
    "parent_id": Issue.parent_jira_issue_id,
    "summary": Issue.summary,
    "assignee": Issue.assignee_account_id,
    "due_at": Issue.due_at,
    "updated_at": Issue.updated_at,
}
OPERATORS = {"eq", "ne", "in", "not_in", "is_null", "contains", "gte", "lte", "between"}


class FilterValidationError(ValueError):
    pass


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def base_query(self, project_ids: list[str] | None = None, filters: dict[str, Any] | None = None) -> Any:
        query = select(Issue.id).where(Issue.is_deleted_or_inaccessible.is_(False))
        if project_ids:
            query = query.where(Issue.project_jira_id.in_(project_ids))
        if filters:
            query = query.where(self.compile_filter(filters))
        return query

    def compile_filter(self, node: dict[str, Any]) -> Any:
        if not isinstance(node, dict):
            raise FilterValidationError("Filter node must be an object")
        boolean_keys = [key for key in ("and", "or", "not") if key in node]
        if boolean_keys:
            if len(boolean_keys) != 1 or len(node) != 1:
                raise FilterValidationError("Boolean filter nodes must contain exactly one operator")
            key = boolean_keys[0]
            if key == "not":
                return not_(self.compile_filter(node[key]))
            children = node[key]
            if not isinstance(children, list) or not children:
                raise FilterValidationError(f"'{key}' requires a non-empty array")
            expressions = [self.compile_filter(child) for child in children]
            return and_(*expressions) if key == "and" else or_(*expressions)
        field_id, operator = node.get("field_id"), node.get("operator")
        if not isinstance(field_id, str) or operator not in OPERATORS:
            raise FilterValidationError("Leaf filters require a known field_id and supported operator")
        if field_id in CORE_FIELDS:
            return self._core_expression(CORE_FIELDS[field_id], operator, node.get("value"))
        field = self.db.scalar(select(JiraField).where(JiraField.jira_field_id == field_id))
        if field is None:
            raise FilterValidationError(f"Unknown Jira field '{field_id}'")
        return self._custom_expression(field, operator, node.get("value"))

    def _core_expression(self, column: Any, operator: str, value: Any) -> Any:
        converted = self._convert_core(column, value)
        if operator == "is_null":
            return column.is_(None) if value is not False else column.is_not(None)
        if operator == "eq":
            return column == converted
        if operator == "ne":
            return column != converted
        if operator == "in":
            return column.in_(self._list(value))
        if operator == "not_in":
            return ~column.in_(self._list(value))
        if operator == "contains":
            return cast(column, String).ilike(f"%{value}%")
        if operator == "gte":
            return column >= converted
        if operator == "lte":
            return column <= converted
        if operator == "between":
            values = self._list(value)
            if len(values) != 2:
                raise FilterValidationError("between requires exactly two values")
            return column.between(self._convert_core(column, values[0]), self._convert_core(column, values[1]))
        raise FilterValidationError(f"Unsupported operator '{operator}'")

    def _custom_expression(self, field: JiraField, operator: str, value: Any) -> Any:
        item = aliased(IssueFieldValue)
        column = self._value_column(item, field.schema_json)
        if operator == "is_null":
            has_value = exists(
                select(1).where(
                    item.issue_id == Issue.id, item.jira_field_id == field.jira_field_id, item.value_type != "null", column.is_not(None)
                )
            )
            return ~has_value if value is not False else has_value
        converted = self._convert_custom(field.schema_json, value)
        if operator == "eq":
            predicate = column == converted
        elif operator == "ne":
            predicate = column == converted
        elif operator in {"in", "not_in"}:
            predicate = column.in_([self._convert_custom(field.schema_json, x) for x in self._list(value)])
        elif operator == "contains":
            predicate = cast(column, String).ilike(f"%{value}%")
        elif operator == "gte":
            predicate = column >= converted
        elif operator == "lte":
            predicate = column <= converted
        elif operator == "between":
            values = self._list(value)
            if len(values) != 2:
                raise FilterValidationError("between requires exactly two values")
            predicate = column.between(*(self._convert_custom(field.schema_json, x) for x in values))
        else:
            raise FilterValidationError(f"Unsupported operator '{operator}'")
        match = exists(select(1).where(item.issue_id == Issue.id, item.jira_field_id == field.jira_field_id, predicate))
        return ~match if operator in {"ne", "not_in"} else match

    @staticmethod
    def _value_column(item: Any, schema: dict[str, Any]) -> Any:
        field_type = schema.get("type")
        items_type = schema.get("items")
        effective = items_type if field_type == "array" else field_type
        if effective == "number":
            return item.number_value
        if effective in {"date", "datetime"}:
            return item.date_value
        if effective == "boolean":
            return item.boolean_value
        if effective in {"option", "priority", "resolution"}:
            return item.option_id
        if effective == "user":
            return item.user_account_id
        return item.string_value

    @staticmethod
    def _convert_custom(schema: dict[str, Any], value: Any) -> Any:
        effective = schema.get("items") if schema.get("type") == "array" else schema.get("type")
        if effective == "number":
            return float(value)
        if effective == "boolean":
            return bool(value)
        if effective in {"date", "datetime"}:
            return parse_datetime(value)
        return str(value) if value is not None else None

    @staticmethod
    def _convert_core(column: Any, value: Any) -> Any:
        if column in {Issue.due_at, Issue.updated_at}:
            return parse_datetime(value)
        return value

    @staticmethod
    def _list(value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise FilterValidationError("Operator requires an array value")
        return value

    def count(self, project_ids: list[str] | None = None, filters: dict[str, Any] | None = None) -> int:
        query = self.base_query(project_ids, filters).subquery()
        return self.db.scalar(select(func.count(distinct(query.c.id)))) or 0

    def summary(self, project_ids: list[str] | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        scope_ids = self.base_query(project_ids, filters).subquery()
        total = self.db.scalar(select(func.count(distinct(scope_ids.c.id)))) or 0
        children = aliased(Issue)
        leaves = select(Issue.id).where(
            Issue.id.in_(select(scope_ids.c.id)),
            ~exists(select(1).where(children.parent_jira_issue_id == Issue.jira_issue_id, children.is_deleted_or_inaccessible.is_(False))),
        )
        leaf_count = self.db.scalar(select(func.count()).select_from(leaves.subquery())) or 0
        done = (
            self.db.scalar(
                select(func.count(distinct(Issue.id)))
                .join(JiraStatus, JiraStatus.jira_status_id == Issue.status_jira_id)
                .where(Issue.id.in_(leaves), JiraStatus.category_key == "done")
            )
            or 0
        )
        now = datetime.now(timezone.utc)
        overdue = (
            self.db.scalar(
                select(func.count(distinct(Issue.id)))
                .join(JiraStatus, JiraStatus.jira_status_id == Issue.status_jira_id, isouter=True)
                .where(
                    Issue.id.in_(select(scope_ids.c.id)),
                    Issue.due_at < now,
                    or_(JiraStatus.category_key.is_(None), JiraStatus.category_key != "done"),
                )
            )
            or 0
        )
        missing_due = (
            self.db.scalar(select(func.count(distinct(Issue.id))).where(Issue.id.in_(select(scope_ids.c.id)), Issue.due_at.is_(None))) or 0
        )
        unassigned = (
            self.db.scalar(
                select(func.count(distinct(Issue.id))).where(Issue.id.in_(select(scope_ids.c.id)), Issue.assignee_account_id.is_(None))
            )
            or 0
        )
        latest = self.db.scalar(select(func.max(Issue.synced_at)).where(Issue.id.in_(select(scope_ids.c.id))))
        return {
            "metrics": [
                self._metric("total_work_items", total, total, total, "count", latest),
                self._metric(
                    "leaf_completion",
                    done / leaf_count if leaf_count else None,
                    done,
                    leaf_count,
                    "ratio",
                    latest,
                    ["Numerator uses Jira statusCategory=Done; denominator is distinct leaf issues."],
                ),
                self._metric(
                    "overdue", overdue, overdue, total, "count", latest, [f"{missing_due} scoped issues have no due date and are excluded."]
                ),
                self._metric("unassigned", unassigned, unassigned, total, "count", latest),
            ],
            "scope_count": total,
            "null_counts": {"due_at": missing_due},
            "sync_version": sync_version(self.db),
        }

    @staticmethod
    def _metric(
        metric_id: str, value: Any, numerator: int, denominator: int, unit: str, as_of: datetime | None, warnings: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "metric_id": metric_id,
            "value": value,
            "numerator": numerator,
            "denominator": denominator,
            "unit": unit,
            "as_of": as_of,
            "warnings": warnings or [],
        }

    def group_by(self, field_id: str, project_ids: list[str] | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        scope = self.base_query(project_ids, filters).subquery()
        rows: list[Any]
        if field_id in CORE_FIELDS:
            column = CORE_FIELDS[field_id]
            rows = list(
                self.db.execute(
                    select(column, func.count(distinct(Issue.id)))
                    .where(Issue.id.in_(select(scope.c.id)))
                    .group_by(column)
                    .order_by(func.count(distinct(Issue.id)).desc())
                ).all()
            )
            return self._groups(field_id, rows, False)
        field = self.db.scalar(select(JiraField).where(JiraField.jira_field_id == field_id))
        if field is None:
            raise FilterValidationError(f"Unknown Jira field '{field_id}'")
        column = self._value_column(IssueFieldValue, field.schema_json)
        rows = list(
            self.db.execute(
                select(column, func.max(IssueFieldValue.string_value), func.count(distinct(IssueFieldValue.issue_id)))
                .where(
                    IssueFieldValue.issue_id.in_(select(scope.c.id)),
                    IssueFieldValue.jira_field_id == field_id,
                    IssueFieldValue.value_type != "null",
                )
                .group_by(column)
                .order_by(func.count(distinct(IssueFieldValue.issue_id)).desc())
            ).all()
        )
        present = (
            self.db.scalar(
                select(func.count(distinct(IssueFieldValue.issue_id))).where(
                    IssueFieldValue.issue_id.in_(select(scope.c.id)),
                    IssueFieldValue.jira_field_id == field_id,
                    IssueFieldValue.value_type != "null",
                )
            )
            or 0
        )
        total = self.db.scalar(select(func.count()).select_from(scope)) or 0
        rows.append((None, "No value", total - present))
        return self._groups(field_id, rows, field.schema_json.get("type") == "array")

    def numeric_aggregate(
        self, field_id: str, aggregation: str, project_ids: list[str] | None = None, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if aggregation not in {"sum", "avg", "min", "max"}:
            raise FilterValidationError("Numeric aggregation must be sum, avg, min, or max")
        field = self.db.scalar(select(JiraField).where(JiraField.jira_field_id == field_id))
        if field is None:
            raise FilterValidationError(f"Unknown Jira field '{field_id}'")
        effective = field.schema_json.get("items") if field.schema_json.get("type") == "array" else field.schema_json.get("type")
        if effective != "number":
            raise FilterValidationError("Numeric aggregation requires a numeric Jira field")
        scope = self.base_query(project_ids, filters).subquery()
        expression = {
            "sum": func.sum(IssueFieldValue.number_value),
            "avg": func.avg(IssueFieldValue.number_value),
            "min": func.min(IssueFieldValue.number_value),
            "max": func.max(IssueFieldValue.number_value),
        }[aggregation]
        value = self.db.scalar(
            select(expression).where(
                IssueFieldValue.issue_id.in_(select(scope.c.id)),
                IssueFieldValue.jira_field_id == field_id,
                IssueFieldValue.number_value.is_not(None),
            )
        )
        present = (
            self.db.scalar(
                select(func.count(distinct(IssueFieldValue.issue_id))).where(
                    IssueFieldValue.issue_id.in_(select(scope.c.id)),
                    IssueFieldValue.jira_field_id == field_id,
                    IssueFieldValue.number_value.is_not(None),
                )
            )
            or 0
        )
        total = self.db.scalar(select(func.count()).select_from(scope)) or 0
        return {
            "field_id": field_id,
            "aggregation": aggregation,
            "value": value,
            "distinct_issue_count": present,
            "null_issue_count": total - present,
            "null_treatment": "excluded",
            "sync_version": sync_version(self.db),
        }

    def _groups(self, field_id: str, rows: list[Any], non_additive: bool) -> dict[str, Any]:
        labels: dict[Any, str] = {}
        if field_id == "status_id":
            labels = {row.jira_status_id: row.name for row in self.db.scalars(select(JiraStatus))}
        groups = []
        for row in rows:
            if len(row) == 3:
                value, observed_label, count = row
            else:
                value, count = row
                observed_label = None
            groups.append(
                {
                    "value": value,
                    "label": observed_label or labels.get(value, str(value) if value is not None else "No value"),
                    "issue_count": count,
                }
            )
        return {
            "field_id": field_id,
            "groups": groups,
            "non_additive": non_additive,
            "warnings": ["Multi-value groups overlap; totals are not additive."] if non_additive else [],
            "sync_version": sync_version(self.db),
        }
