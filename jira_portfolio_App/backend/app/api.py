import asyncio
import json
from datetime import datetime, timezone
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .analytics import AnalyticsService, FilterValidationError
from .auth import ALL_SCREENS, authenticate_token, ensure_default_admin, hash_password, issue_session, public_user, verify_password
from .config import Settings, get_settings
from .db import Base, get_db
from .jira import JiraClient
from .metadata import MetadataService
from .models import (
    AppSession,
    AppUser,
    DashboardConfig,
    GridConfig,
    HierarchyAnomaly,
    Issue,
    IssueDateChange,
    IssueFieldValue,
    IssueRelationship,
    JiraConnection,
    JiraField,
    JiraFieldContext,
    JiraIssueType,
    JiraProject,
    JiraStatus,
    MetadataRefresh,
    MetricDefinition,
    ProjectPlan,
    ProjectPlanBaseline,
    SprintGridConfig,
    SprintViewConfig,
    SyncRun,
    TraceabilityConfig,
)
from .schemas import (
    CardSummaryRequest,
    DashboardConfigIn,
    FieldBulkSelection,
    FieldOut,
    GridConfigIn,
    GroupByRequest,
    IssueTypeOut,
    ListEnvelope,
    LoginIn,
    MetricConfigIn,
    ProjectOut,
    ProjectPlanIn,
    SelectionUpdate,
    SprintViewConfigIn,
    StatusOut,
    SyncRequest,
    TraceabilityConfigIn,
    UserIn,
)
from .sync import SyncBusyError, SyncService, sync_version

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]


def current_user(db: Db, authorization: Annotated[str | None, Header()] = None) -> AppUser:
    return authenticate_token(db, authorization)


def require_admin(
    db: Db,
    authorization: Annotated[str | None, Header()] = None,
    x_app_role: Annotated[str | None, Header()] = None,
) -> AppUser | None:
    # X-App-Role remains only for backwards-compatible local tests and scripts.
    if authorization:
        user = authenticate_token(db, authorization)
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required")
        return user
    if x_app_role == "admin":
        return None
    raise HTTPException(status_code=403, detail="Administrator access required")


@router.post("/auth/login")
def login(payload: LoginIn, db: Db) -> dict[str, Any]:
    ensure_default_admin(db)
    user = db.scalar(select(AppUser).where(func.lower(AppUser.username) == payload.username.strip().lower()))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, expires_at = issue_session(db, user)
    return {"token": token, "expires_at": expires_at, "user": public_user(user)}


@router.get("/auth/me")
def me(user: Annotated[AppUser, Depends(current_user)]) -> dict[str, object]:
    return public_user(user)


@router.post("/auth/logout", status_code=204)
def logout(
    db: Db,
    user: Annotated[AppUser, Depends(current_user)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    del user
    if authorization:
        import hashlib

        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        session = db.scalar(select(AppSession).where(AppSession.token_hash == token_hash))
        if session:
            db.delete(session)
            db.commit()
    return Response(status_code=204)


@router.get("/admin/users", dependencies=[Depends(require_admin)])
def list_users(db: Db) -> dict[str, Any]:
    ensure_default_admin(db)
    users = list(db.scalars(select(AppUser).order_by(AppUser.username)))
    return {"items": [public_user(user) for user in users], "screens": ALL_SCREENS}


def validate_user_input(payload: UserIn) -> None:
    if payload.role not in {"admin", "user"}:
        raise HTTPException(status_code=422, detail="Role must be admin or user")
    invalid = sorted(set(payload.screen_permissions) - set(ALL_SCREENS))
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown screen permissions: {', '.join(invalid)}")


@router.post("/admin/users", dependencies=[Depends(require_admin)], status_code=201)
def create_user(payload: UserIn, db: Db) -> dict[str, object]:
    validate_user_input(payload)
    if not payload.password:
        raise HTTPException(status_code=422, detail="Password is required for a new user")
    username = payload.username.strip().lower()
    if db.scalar(select(AppUser).where(AppUser.username == username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = AppUser(
        username=username,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        screen_permissions_json=ALL_SCREENS if payload.role == "admin" else payload.screen_permissions,
        active=payload.active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return public_user(user)


@router.put("/admin/users/{user_id}", dependencies=[Depends(require_admin)])
def update_user(user_id: int, payload: UserIn, db: Db) -> dict[str, object]:
    validate_user_input(payload)
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    username = payload.username.strip().lower()
    duplicate = db.scalar(select(AppUser).where(AppUser.username == username, AppUser.id != user_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="Username already exists")
    user.username = username
    user.display_name = payload.display_name.strip()
    user.role = payload.role
    user.screen_permissions_json = ALL_SCREENS if payload.role == "admin" else payload.screen_permissions
    user.active = payload.active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return public_user(user)


@router.delete("/admin/users/{user_id}", dependencies=[Depends(require_admin)], status_code=204)
def delete_user(user_id: int, db: Db) -> Response:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="The default administrator cannot be deleted")
    db.delete(user)
    db.commit()
    return Response(status_code=204)


async def jira_client(settings: Annotated[Settings, Depends(get_settings)]) -> AsyncIterator[JiraClient]:
    if not settings.jira_is_configured:
        raise HTTPException(status_code=503, detail="Jira credentials are not configured on the server")
    async with JiraClient(
        settings.jira_base_url or "",
        settings.jira_email or "",
        settings.jira_api_token or "",
        max_retries=settings.jira_max_retries,
        timeout=settings.jira_timeout_seconds,
    ) as client:
        yield client


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Db) -> dict[str, Any]:
    db.scalar(select(1))
    return {"status": "ready", "jira_configured": get_settings().jira_is_configured}


@router.post("/jira/test-connection", dependencies=[Depends(require_admin)])
async def test_connection(client: Annotated[JiraClient, Depends(jira_client)], db: Db) -> dict[str, Any]:
    profile = await client.myself()
    settings = get_settings()
    connection = db.scalar(select(JiraConnection).where(JiraConnection.base_url == settings.jira_base_url))
    if connection is None:
        connection = JiraConnection(base_url=settings.jira_base_url or "")
        db.add(connection)
        db.commit()
    return {
        "connected": True,
        "base_url": settings.jira_base_url,
        "account": {"account_id": profile.get("accountId"), "display_name": profile.get("displayName")},
    }


@router.get("/jira/issues/{issue_id_or_key}/metadata")
async def live_issue_metadata(
    issue_id_or_key: str,
    client: Annotated[JiraClient, Depends(jira_client)],
) -> dict[str, Any]:
    """Proxy current Jira issue metadata; the payload is intentionally not stored."""
    issue = await client.issue_metadata(issue_id_or_key)
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    names = issue.get("names") if isinstance(issue.get("names"), dict) else {}
    schema = issue.get("schema") if isinstance(issue.get("schema"), dict) else {}
    return {
        "id": issue.get("id"),
        "key": issue.get("key", issue_id_or_key),
        "self": issue.get("self"),
        "fields": fields,
        "names": names,
        "schema": schema,
    }


@router.get("/jira/portfolio-metrics", dependencies=[Depends(current_user)])
async def live_portfolio_metrics(
    db: Db,
    client: Annotated[JiraClient, Depends(jira_client)],
) -> dict[str, Any]:
    """Return Jira-evaluated JQL counts for every locally enabled project.

    Only the active-project selection comes from SQLite. Counts are requested from
    Jira on every call and are never persisted by this application.
    """
    projects = list(db.scalars(select(JiraProject).where(JiraProject.active.is_(True)).order_by(JiraProject.name)))
    semaphore = asyncio.Semaphore(4)

    async def metrics_for(project: JiraProject) -> dict[str, Any]:
        project_clause = f"project = {int(project.jira_project_id)}"
        queries = {
            "total": project_clause,
            "open": f'{project_clause} AND resolution is EMPTY',
            "to_do": f'{project_clause} AND statusCategory = "To Do"',
            "in_progress": f'{project_clause} AND statusCategory = "In Progress"',
            "done": f'{project_clause} AND statusCategory = Done',
            "overdue": f'{project_clause} AND due < startOfDay() AND statusCategory != Done',
            "due_today": f'{project_clause} AND due >= startOfDay() AND due <= endOfDay() AND statusCategory != Done',
            "due_next_7_days": f'{project_clause} AND due > endOfDay() AND due <= endOfDay("+7d") AND statusCategory != Done',
            "due_next_30_days": f'{project_clause} AND due > endOfDay() AND due <= endOfDay("+30d") AND statusCategory != Done',
            "open_with_due_date": f'{project_clause} AND due is not EMPTY AND statusCategory != Done',
            "no_due_date": f'{project_clause} AND due is EMPTY AND statusCategory != Done',
            "unassigned": f'{project_clause} AND assignee is EMPTY AND statusCategory != Done',
            "created_last_7_days": f'{project_clause} AND created >= -7d',
            "created_last_30_days": f'{project_clause} AND created >= -30d',
            "updated_last_7_days": f'{project_clause} AND updated >= -7d',
            "stale_open_30_days": f'{project_clause} AND updated < -30d AND statusCategory != Done',
            "resolved_last_7_days": f'{project_clause} AND resolved >= -7d',
            "resolved_last_30_days": f'{project_clause} AND resolved >= -30d',
        }
        async with semaphore:
            counts = {name: await client.approximate_issue_count(jql) for name, jql in queries.items()}
        return {
            "project_id": project.jira_project_id,
            "key": project.key,
            "name": project.name,
            "metrics": counts,
        }

    items = await asyncio.gather(*(metrics_for(project) for project in projects))
    return {
        "source": "jira_live",
        "count_method": "jira_jql_approximate_count",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


@router.post("/admin/metadata/refresh", dependencies=[Depends(require_admin)])
async def refresh_metadata(client: Annotated[JiraClient, Depends(jira_client)], db: Db) -> dict[str, Any]:
    run = await MetadataService(db, client).refresh()
    return {"refresh_id": run.id, "status": run.status, "counts": run.counts_json, "warnings": run.warnings_json}


def version(db: Session) -> int:
    return max(db.scalar(select(func.max(MetadataRefresh.id)).where(MetadataRefresh.status == "succeeded")) or 0, sync_version(db))


@router.get("/jira/projects", response_model=ListEnvelope[ProjectOut])
def projects(db: Db) -> ListEnvelope[ProjectOut]:
    items = list(db.scalars(select(JiraProject).order_by(JiraProject.name)))
    return ListEnvelope(items=[ProjectOut.model_validate(x) for x in items], total_count=len(items), sync_version=version(db))


def project_plan_payload(project: JiraProject, plan: ProjectPlan | None, db: Session) -> dict[str, Any]:
    baselines = [] if plan is None else list(
        db.scalars(select(ProjectPlanBaseline).where(ProjectPlanBaseline.project_plan_id == plan.id).order_by(ProjectPlanBaseline.version))
    )
    return {
        "project_id": project.jira_project_id,
        "key": project.key,
        "name": project.name,
        "start_date": plan.start_date.isoformat() if plan else None,
        "project_status": plan.project_status if plan else None,
        "management_support": plan.management_support if plan else "",
        "baseline_date": baselines[0].end_date.isoformat() if baselines else None,
        "latest_baseline_date": baselines[-1].end_date.isoformat() if baselines else None,
        "latest_baseline_version": baselines[-1].version if baselines else 0,
        "baselines": [
            {"version": item.version, "end_date": item.end_date.isoformat(), "created_at": item.created_at.isoformat()}
            for item in baselines
        ],
    }


@router.get("/project-plans", dependencies=[Depends(current_user)])
def list_project_plans(db: Db) -> dict[str, Any]:
    active_projects = list(db.scalars(select(JiraProject).where(JiraProject.active.is_(True)).order_by(JiraProject.name)))
    plans = {
        item.project_jira_id: item
        for item in db.scalars(select(ProjectPlan).where(ProjectPlan.project_jira_id.in_([project.jira_project_id for project in active_projects])))
    } if active_projects else {}
    return {"items": [project_plan_payload(project, plans.get(project.jira_project_id), db) for project in active_projects]}


@router.get("/documentation/data-model", dependencies=[Depends(current_user)])
def live_data_model(db: Db) -> dict[str, Any]:
    """Describe the running SQLAlchemy model and current SQLite row counts."""
    tables = sorted(Base.metadata.tables.values(), key=lambda item: item.name)
    nodes = []
    links = []
    for table in tables:
        nodes.append(
            {
                "id": table.name,
                "row_count": db.scalar(select(func.count()).select_from(table)) or 0,
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "primary_key": column.primary_key,
                        "nullable": column.nullable,
                    }
                    for column in table.columns
                ],
            }
        )
        for foreign_key in table.foreign_keys:
            links.append(
                {
                    "source": table.name,
                    "target": foreign_key.column.table.name,
                    "source_column": foreign_key.parent.name,
                    "target_column": foreign_key.column.name,
                }
            )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": "SQLite",
        "nodes": nodes,
        "links": links,
    }


@router.put("/admin/project-plans/{jira_project_id}", dependencies=[Depends(require_admin)])
def save_project_plan(jira_project_id: str, payload: ProjectPlanIn, db: Db) -> dict[str, Any]:
    project = db.scalar(select(JiraProject).where(JiraProject.jira_project_id == jira_project_id, JiraProject.active.is_(True)))
    if project is None:
        raise HTTPException(404, "Active project not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "Baseline end date cannot be before the project start date")
    plan = db.scalar(select(ProjectPlan).where(ProjectPlan.project_jira_id == jira_project_id))
    if plan is None:
        plan = ProjectPlan(project_jira_id=jira_project_id, start_date=payload.start_date)
        db.add(plan)
        db.flush()
    else:
        earliest_end = db.scalar(select(func.min(ProjectPlanBaseline.end_date)).where(ProjectPlanBaseline.project_plan_id == plan.id))
        if earliest_end is not None and payload.start_date > earliest_end:
            raise HTTPException(422, "Project start date cannot be after an existing baseline end date")
        plan.start_date = payload.start_date
    plan.project_status = payload.project_status
    plan.management_support = payload.management_support.strip()
    latest = db.scalar(
        select(ProjectPlanBaseline).where(ProjectPlanBaseline.project_plan_id == plan.id).order_by(ProjectPlanBaseline.version.desc())
    )
    if latest is None or latest.end_date != payload.end_date:
        db.add(ProjectPlanBaseline(project_plan_id=plan.id, version=(latest.version + 1 if latest else 1), end_date=payload.end_date))
    db.commit()
    db.refresh(plan)
    return project_plan_payload(project, plan, db)


@router.put("/admin/projects/{jira_project_id}", dependencies=[Depends(require_admin)])
def select_project(jira_project_id: str, update: SelectionUpdate, db: Db) -> ProjectOut:
    row = db.scalar(select(JiraProject).where(JiraProject.jira_project_id == jira_project_id))
    if row is None:
        raise HTTPException(404, "Project not found")
    row.active = update.selected
    db.commit()
    return ProjectOut.model_validate(row)


@router.delete("/admin/projects/{jira_project_id}/data", dependencies=[Depends(require_admin)])
def delete_project_data(jira_project_id: str, db: Db, confirm: str = Query(...)) -> dict[str, Any]:
    """Permanently remove one project's local SQLite data without writing to Jira."""
    if confirm != jira_project_id:
        raise HTTPException(400, "Confirmation must exactly match the Jira project ID")
    project = db.scalar(select(JiraProject).where(JiraProject.jira_project_id == jira_project_id))
    if project is None:
        raise HTTPException(404, "Project not found")
    project_key = project.key

    issue_ids = list(db.scalars(select(Issue.id).where(Issue.project_jira_id == jira_project_id)))
    counts = {
        "issues": len(issue_ids),
        "field_values": 0,
        "date_changes": 0,
        "relationships": 0,
        "anomalies": 0,
        "configurations": 0,
        "field_contexts_removed": 0,
        "field_contexts_updated": 0,
    }
    if issue_ids:
        counts["field_values"] = db.execute(delete(IssueFieldValue).where(IssueFieldValue.issue_id.in_(issue_ids))).rowcount
        counts["date_changes"] = db.execute(delete(IssueDateChange).where(IssueDateChange.issue_id.in_(issue_ids))).rowcount
        counts["relationships"] = db.execute(
            delete(IssueRelationship).where(
                or_(IssueRelationship.child_issue_id.in_(issue_ids), IssueRelationship.parent_issue_id.in_(issue_ids))
            )
        ).rowcount
        counts["anomalies"] = db.execute(delete(HierarchyAnomaly).where(HierarchyAnomaly.issue_id.in_(issue_ids))).rowcount
        db.execute(delete(Issue).where(Issue.id.in_(issue_ids)))

    for model in (TraceabilityConfig, GridConfig, SprintGridConfig, SprintViewConfig):
        counts["configurations"] += db.execute(delete(model).where(model.project_jira_id == jira_project_id)).rowcount

    for context in list(db.scalars(select(JiraFieldContext))):
        project_ids = list(context.project_ids_json or [])
        if jira_project_id not in project_ids:
            continue
        remaining = [project_id for project_id in project_ids if project_id != jira_project_id]
        if remaining:
            context.project_ids_json = remaining
            counts["field_contexts_updated"] += 1
        else:
            db.delete(context)
            counts["field_contexts_removed"] += 1

    db.delete(project)
    db.commit()
    return {"status": "deleted", "project_id": jira_project_id, "project_key": project_key, "deleted": counts}


def traceability_config_dict(row: TraceabilityConfig | None, project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "grouping_fields": row.grouping_fields_json if row else ["labels", "status_id", "issue_type_id"],
        "level_captions": row.level_captions_json if row else [],
        "updated_at": row.updated_at if row else None,
        "persisted": row is not None,
    }


MANDATORY_GRID_COLUMNS = ["key", "summary", "issue_type", "baseline_due", "revised_due", "status"]


def applicable_grid_field_ids(project_id: str, db: Session) -> set[str]:
    raw_fields: list[dict[str, Any]] = list(
        db.scalars(
            select(Issue.raw_fields_json).where(
                Issue.project_jira_id == project_id, Issue.is_deleted_or_inaccessible.is_(False)
            )
        )
    )
    return {field_id for raw in raw_fields for field_id in (raw or {})}


def grid_config_dict(row: GridConfig | None, project_id: str, db: Session) -> dict[str, Any]:
    optional_fields = row.optional_fields_json if row else []
    names = {field.jira_field_id: field.name for field in db.scalars(select(JiraField).where(JiraField.jira_field_id.in_(optional_fields)))}
    return {
        "project_id": project_id,
        "mandatory_columns": MANDATORY_GRID_COLUMNS,
        "optional_fields": [{"field_id": field_id, "name": names.get(field_id, field_id)} for field_id in optional_fields],
        "updated_at": row.updated_at if row else None,
        "persisted": row is not None,
    }


def sprint_grid_config_dict(row: SprintGridConfig | None, project_id: str, db: Session) -> dict[str, Any]:
    optional_fields = row.optional_fields_json if row else []
    names = {
        field.jira_field_id: field.name
        for field in db.scalars(select(JiraField).where(JiraField.jira_field_id.in_(optional_fields)))
    }
    return {
        "project_id": project_id,
        "mandatory_columns": MANDATORY_GRID_COLUMNS,
        "optional_fields": [{"field_id": field_id, "name": names.get(field_id, field_id)} for field_id in optional_fields],
        "updated_at": row.updated_at if row else None,
        "persisted": row is not None,
    }


def default_sprint_fields(db: Session) -> list[str]:
    sprint = db.scalar(select(JiraField).where(func.lower(JiraField.name) == "sprint"))
    return [sprint.jira_field_id, "status_id", "issue_type_id"] if sprint else ["status_id", "issue_type_id"]


def sprint_view_config_dict(row: SprintViewConfig | None, project_id: str, db: Session) -> dict[str, Any]:
    grouping_fields = row.grouping_fields_json if row else default_sprint_fields(db)
    captions = row.level_captions_json if row else []
    return {
        "project_id": project_id,
        "grouping_fields": grouping_fields,
        "level_captions": captions,
        "updated_at": row.updated_at if row else None,
        "persisted": row is not None,
    }


@router.get("/sprint-view-config/{project_id}")
def get_sprint_view_config(project_id: str, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(SprintViewConfig).where(SprintViewConfig.project_jira_id == project_id))
    return sprint_view_config_dict(row, project_id, db)


@router.put("/admin/sprint-view-config/{project_id}", dependencies=[Depends(require_admin)])
def save_sprint_view_config(project_id: str, update: SprintViewConfigIn, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    if len(update.grouping_fields) != len(set(update.grouping_fields)):
        raise HTTPException(422, "Sprint grouping fields must be unique")
    if update.level_captions and len(update.level_captions) != len(update.grouping_fields):
        raise HTTPException(422, "Level captions must match the number of grouping fields")
    raw_system_fields = {
        "summary", "project", "issuetype", "status", "parent", "assignee", "reporter", "created", "updated", "duedate",
        "resolutiondate",
    }
    allowed = (applicable_grid_field_ids(project_id, db) - raw_system_fields) | {"status_id", "issue_type_id", "assignee"}
    invalid = [field_id for field_id in update.grouping_fields if field_id not in allowed]
    if invalid:
        raise HTTPException(422, f"Fields are not applicable to this project: {', '.join(invalid)}")
    captions = [caption.strip() for caption in update.level_captions] if update.level_captions else [""] * len(update.grouping_fields)
    if any(len(caption) > 100 for caption in captions):
        raise HTTPException(422, "Level captions must be 100 characters or fewer")
    row = db.scalar(select(SprintViewConfig).where(SprintViewConfig.project_jira_id == project_id))
    if row is None:
        row = SprintViewConfig(project_jira_id=project_id, grouping_fields_json=update.grouping_fields, level_captions_json=captions)
        db.add(row)
    else:
        row.grouping_fields_json = update.grouping_fields
        row.level_captions_json = captions
    db.commit()
    db.refresh(row)
    return sprint_view_config_dict(row, project_id, db)


@router.get("/grid-config/{project_id}")
def get_grid_config(project_id: str, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(GridConfig).where(GridConfig.project_jira_id == project_id))
    return grid_config_dict(row, project_id, db)


@router.get("/grid-config/{project_id}/fields", response_model=ListEnvelope[FieldOut])
def grid_config_fields(project_id: str, db: Db) -> ListEnvelope[FieldOut]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    applicable = applicable_grid_field_ids(project_id, db)
    rows = list(db.scalars(select(JiraField).where(JiraField.jira_field_id.in_(applicable)).order_by(JiraField.name)))
    return ListEnvelope(items=[FieldOut.model_validate(row) for row in rows], total_count=len(rows), sync_version=version(db))


@router.put("/admin/grid-config/{project_id}", dependencies=[Depends(require_admin)])
def save_grid_config(project_id: str, update: GridConfigIn, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    if len(update.optional_fields) != len(set(update.optional_fields)):
        raise HTTPException(422, "Grid fields must be unique")
    discovered = set(db.scalars(select(JiraField.jira_field_id)))
    unknown = [field_id for field_id in update.optional_fields if field_id not in discovered]
    if unknown:
        raise HTTPException(422, f"Unknown grid fields: {', '.join(unknown)}")
    applicable = applicable_grid_field_ids(project_id, db)
    invalid = [field_id for field_id in update.optional_fields if field_id not in applicable]
    if invalid:
        raise HTTPException(422, f"Fields are not applicable to this project: {', '.join(invalid)}")
    row = db.scalar(select(GridConfig).where(GridConfig.project_jira_id == project_id))
    if row is None:
        row = GridConfig(project_jira_id=project_id, optional_fields_json=update.optional_fields)
        db.add(row)
    else:
        row.optional_fields_json = update.optional_fields
    db.commit()
    db.refresh(row)
    return grid_config_dict(row, project_id, db)


@router.get("/sprint-grid-config/{project_id}")
def get_sprint_grid_config(project_id: str, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(SprintGridConfig).where(SprintGridConfig.project_jira_id == project_id))
    return sprint_grid_config_dict(row, project_id, db)


@router.put("/admin/sprint-grid-config/{project_id}", dependencies=[Depends(require_admin)])
def save_sprint_grid_config(project_id: str, update: GridConfigIn, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    if len(update.optional_fields) != len(set(update.optional_fields)):
        raise HTTPException(422, "Grid fields must be unique")
    discovered = set(db.scalars(select(JiraField.jira_field_id)))
    unknown = [field_id for field_id in update.optional_fields if field_id not in discovered]
    if unknown:
        raise HTTPException(422, f"Unknown grid fields: {', '.join(unknown)}")
    applicable = applicable_grid_field_ids(project_id, db)
    invalid = [field_id for field_id in update.optional_fields if field_id not in applicable]
    if invalid:
        raise HTTPException(422, f"Fields are not applicable to this project: {', '.join(invalid)}")
    row = db.scalar(select(SprintGridConfig).where(SprintGridConfig.project_jira_id == project_id))
    if row is None:
        row = SprintGridConfig(project_jira_id=project_id, optional_fields_json=update.optional_fields)
        db.add(row)
    else:
        row.optional_fields_json = update.optional_fields
    db.commit()
    db.refresh(row)
    return sprint_grid_config_dict(row, project_id, db)


@router.get("/traceability-config/{project_id}")
def get_traceability_config(project_id: str, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(TraceabilityConfig).where(TraceabilityConfig.project_jira_id == project_id))
    return traceability_config_dict(row, project_id)


@router.get("/portfolio/wbs-flow/{project_id}")
def portfolio_wbs_flow(project_id: str, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(TraceabilityConfig).where(TraceabilityConfig.project_jira_id == project_id))
    fields = row.grouping_fields_json if row else ["labels", "status_id", "issue_type_id"]
    saved_captions = row.level_captions_json if row else []
    discovered_names = {field.jira_field_id: field.name for field in db.scalars(select(JiraField))}
    core_names = {"status_id": "Status", "issue_type_id": "Issue type", "assignee": "Assignee"}
    captions = [
        saved_captions[index].strip()
        if index < len(saved_captions) and saved_captions[index].strip()
        else core_names.get(field_id, discovered_names.get(field_id, field_id))
        for index, field_id in enumerate(fields)
    ]
    return AnalyticsService(db).wbs_flow(project_id, fields, captions)


@router.get("/integrations/grafana/traceability/{project_id}", include_in_schema=False)
@router.get("/integrations/grafana/traceability/cards/{project_id}")
def grafana_traceability(
    project_id: str,
    db: Db,
) -> dict[str, Any]:
    project = db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id))
    if project is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(TraceabilityConfig).where(TraceabilityConfig.project_jira_id == project_id))
    fields = row.grouping_fields_json if row else ["labels", "status_id", "issue_type_id"]
    saved_captions = row.level_captions_json if row else []
    discovered_names = {field.jira_field_id: field.name for field in db.scalars(select(JiraField))}
    core_names = {"status_id": "Status", "issue_type_id": "Issue type", "assignee": "Assignee"}
    captions = [
        saved_captions[index].strip()
        if index < len(saved_captions) and saved_captions[index].strip()
        else core_names.get(field_id, discovered_names.get(field_id, field_id))
        for index, field_id in enumerate(fields)
    ]
    levels = [{"field_id": field_id, "caption": captions[index]} for index, field_id in enumerate(fields)]
    service = AnalyticsService(db)
    status_by_id = {item.jira_status_id: item for item in db.scalars(select(JiraStatus))}
    type_by_id = {item.jira_type_id: item for item in db.scalars(select(JiraIssueType))}
    grid_row = db.scalar(select(GridConfig).where(GridConfig.project_jira_id == project_id))
    grid_configuration = grid_config_dict(grid_row, project_id, db)
    optional_field_ids = [item["field_id"] for item in grid_configuration["optional_fields"]]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    flat_cards: list[dict[str, Any]] = []

    def combine_filter(parent_filter: dict[str, Any] | None, field_id: str, value: Any) -> dict[str, Any]:
        current = (
            {"field_id": field_id, "operator": "is_null", "value": True}
            if value is None
            else {"field_id": field_id, "operator": "eq", "value": value}
        )
        return {"and": [parent_filter, current]} if parent_filter else current

    def work_item_dict(issue: Issue) -> dict[str, Any]:
        status = status_by_id.get(issue.status_jira_id) if issue.status_jira_id else None
        issue_type = type_by_id.get(issue.issue_type_jira_id) if issue.issue_type_jira_id else None
        return {
            "jira_issue_id": issue.jira_issue_id,
            "issue_key": issue.issue_key,
            "summary": issue.summary,
            "parent_jira_issue_id": issue.parent_jira_issue_id,
            "issue_type": {
                "id": issue.issue_type_jira_id,
                "name": issue_type.name if issue_type else None,
                "hierarchy_level": issue_type.hierarchy_level if issue_type else None,
            },
            "status": {
                "id": issue.status_jira_id,
                "name": status.name if status else None,
                "category_key": status.category_key if status else None,
            },
            "baseline_due_at": issue.baseline_due_at,
            "revised_due_at": issue.due_at,
            "updated_at": issue.updated_at,
            "configured_fields": {field_id: issue.raw_fields_json.get(field_id) for field_id in optional_field_ids},
        }

    def build_cards(
        level: int,
        parent_filter: dict[str, Any] | None = None,
        parent_node_id: str | None = None,
        path: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        field_id = fields[level]
        next_field_id = fields[level + 1] if level + 1 < len(fields) else None
        grouped = service.group_by(field_id, [project_id], parent_filter)
        cards: list[dict[str, Any]] = []
        for group in grouped["groups"]:
            if not group["issue_count"]:
                continue
            card_filter = combine_filter(parent_filter, field_id, group["value"])
            card_path = [*(path or []), {"field_id": field_id, "value": group["value"], "label": group["label"]}]
            node_id = f"node-{len(nodes) + 1}"
            metrics = service.card_summary([project_id], card_filter, next_field_id)
            card: dict[str, Any] = {
                "id": node_id,
                "level": level,
                "level_number": level + 1,
                "field_id": field_id,
                "caption": captions[level],
                "value": group["value"],
                "label": group["label"],
                "issue_count": group["issue_count"],
                "path": card_path,
                "filter": card_filter,
                "metrics": metrics,
                "multi_value_groups_overlap": grouped["non_additive"],
                "warnings": grouped["warnings"],
            }
            nodes.append(
                {
                    "id": node_id,
                    "title": group["label"],
                    "subTitle": captions[level],
                    "mainStat": metrics["task_count"],
                    "secondaryStat": group["issue_count"],
                    "level": level,
                    "field_id": field_id,
                    "value": group["value"],
                }
            )
            if parent_node_id:
                edges.append(
                    {
                        "id": f"{parent_node_id}->{node_id}",
                        "source": parent_node_id,
                        "target": node_id,
                        "mainStat": group["issue_count"],
                    }
                )
            if next_field_id:
                card["children"] = build_cards(level + 1, card_filter, node_id, card_path)
            else:
                issue_query = select(Issue).where(
                    Issue.project_jira_id == project_id,
                    Issue.is_deleted_or_inaccessible.is_(False),
                    service.compile_filter(card_filter),
                ).order_by(Issue.issue_key)
                card["work_items"] = [work_item_dict(issue) for issue in db.scalars(issue_query)]
            flat_cards.append({key: value for key, value in card.items() if key not in {"children", "work_items"}})
            cards.append(card)
        return cards

    root_cards = build_cards(0) if fields else []
    issue_count = service.count([project_id])
    return {
        "schema_version": "2.0",
        "view": "traceability_cards",
        "project": {"id": project.jira_project_id, "key": project.key, "name": project.name},
        "configuration": {
            "levels": levels,
            "grid": grid_configuration,
            "persisted": row is not None,
            "updated_at": row.updated_at if row else None,
        },
        "summary": {
            "issue_count": issue_count,
            "level_count": len(levels),
            "card_count": len(flat_cards),
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "traceability": {"cards": root_cards, "flat_cards": flat_cards},
        "nodes": nodes,
        "edges": edges,
        "sync_version": sync_version(db),
        "grafana": {
            "recommended_visualizations": ["Node graph", "Table", "Stat"],
            "node_frame": "nodes",
            "edge_frame": "edges",
            "card_frame": "traceability.flat_cards",
            "work_item_jsonpath": "$.traceability.cards..work_items[*]",
            "refresh_after_sync": True,
        },
    }


@router.get("/integrations/grafana/wbs/{project_id}")
def grafana_wbs(project_id: str, db: Db) -> dict[str, Any]:
    project = db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id))
    if project is None:
        raise HTTPException(404, "Project not found")
    row = db.scalar(select(TraceabilityConfig).where(TraceabilityConfig.project_jira_id == project_id))
    fields = row.grouping_fields_json if row else ["labels", "status_id", "issue_type_id"]
    saved_captions = row.level_captions_json if row else []
    discovered_names = {field.jira_field_id: field.name for field in db.scalars(select(JiraField))}
    core_names = {"status_id": "Status", "issue_type_id": "Issue type", "assignee": "Assignee"}
    captions = [
        saved_captions[index].strip()
        if index < len(saved_captions) and saved_captions[index].strip()
        else core_names.get(field_id, discovered_names.get(field_id, field_id))
        for index, field_id in enumerate(fields)
    ]
    flow = AnalyticsService(db).wbs_flow(project_id, fields, captions)
    nodes = [
        {
            "id": node["id"],
            "title": node["label"],
            "subTitle": captions[node["level"]],
            "mainStat": node["value"],
            "level": node["level"],
            "field_id": fields[node["level"]],
        }
        for node in flow["nodes"]
    ]
    edges = [
        {
            "id": f'{edge["source"]}->{edge["target"]}',
            "source": edge["source"],
            "target": edge["target"],
            "mainStat": edge["value"],
        }
        for edge in flow["links"]
    ]
    return {
        "schema_version": "1.0",
        "view": "wbs_flow",
        "project": {"id": project.jira_project_id, "key": project.key, "name": project.name},
        "configuration": {
            "levels": flow["levels"],
            "persisted": row is not None,
            "updated_at": row.updated_at if row else None,
        },
        "summary": {"issue_count": flow["issue_count"], "node_count": len(nodes), "edge_count": len(edges)},
        "nodes": nodes,
        "edges": edges,
        "sync_version": flow["sync_version"],
        "grafana": {
            "recommended_visualization": "Node graph",
            "node_frame": "nodes",
            "edge_frame": "edges",
            "refresh_after_sync": True,
        },
    }


@router.put("/admin/traceability-config/{project_id}", dependencies=[Depends(require_admin)])
def save_traceability_config(project_id: str, update: TraceabilityConfigIn, db: Db) -> dict[str, Any]:
    if db.scalar(select(JiraProject).where(JiraProject.jira_project_id == project_id)) is None:
        raise HTTPException(404, "Project not found")
    core_fields = {"status_id", "issue_type_id", "assignee"}
    discovered = set(db.scalars(select(JiraField.jira_field_id)))
    unknown = [field_id for field_id in update.grouping_fields if field_id not in core_fields | discovered]
    if unknown:
        raise HTTPException(422, f"Unknown grouping fields: {', '.join(unknown)}")
    if update.level_captions and len(update.level_captions) != len(update.grouping_fields):
        raise HTTPException(422, "Level captions must match the number of grouping fields")
    captions = [caption.strip() for caption in update.level_captions] if update.level_captions else [""] * len(update.grouping_fields)
    if any(len(caption) > 100 for caption in captions):
        raise HTTPException(422, "Level captions must be 100 characters or fewer")
    row = db.scalar(select(TraceabilityConfig).where(TraceabilityConfig.project_jira_id == project_id))
    if row is None:
        row = TraceabilityConfig(project_jira_id=project_id, grouping_fields_json=update.grouping_fields, level_captions_json=captions)
        db.add(row)
    else:
        row.grouping_fields_json = update.grouping_fields
        row.level_captions_json = captions
    db.commit()
    db.refresh(row)
    return traceability_config_dict(row, project_id)


@router.get("/metadata/fields", response_model=ListEnvelope[FieldOut])
def fields(
    db: Db,
    project_id: str | None = None,
    issue_type_id: str | None = None,
    search: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    cursor: int = Query(0, ge=0),
) -> ListEnvelope[FieldOut]:
    query = select(JiraField)
    if search:
        query = query.where(or_(JiraField.name.ilike(f"%{search}%"), JiraField.jira_field_id.ilike(f"%{search}%")))
    if project_id or issue_type_id:
        allowed = applicable_grid_field_ids(project_id, db) if project_id else set()
        context_rows = db.scalars(select(JiraFieldContext))
        for row in context_rows:
            if row.availability != "available":
                continue
            if (not project_id or not row.project_ids_json or project_id in row.project_ids_json) and (
                not issue_type_id or not row.issue_type_ids_json or issue_type_id in row.issue_type_ids_json
            ):
                allowed.add(row.jira_field_id)
        query = query.where(or_(JiraField.is_custom.is_(False), JiraField.jira_field_id.in_(allowed)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(JiraField.name).offset(cursor).limit(limit)))
    next_cursor = str(cursor + limit) if cursor + limit < total else None
    return ListEnvelope(
        items=[FieldOut.model_validate(x) for x in rows], next_cursor=next_cursor, total_count=total, sync_version=version(db)
    )


@router.put("/admin/fields/{jira_field_id}", dependencies=[Depends(require_admin)])
def select_field(jira_field_id: str, update: SelectionUpdate, db: Db) -> FieldOut:
    row = db.scalar(select(JiraField).where(JiraField.jira_field_id == jira_field_id))
    if row is None:
        raise HTTPException(404, "Field not found")
    row.selected = update.selected
    db.commit()
    return FieldOut.model_validate(row)


@router.put("/admin/fields", dependencies=[Depends(require_admin)])
def select_fields(update: FieldBulkSelection, db: Db) -> dict[str, int | bool]:
    rows = list(db.scalars(select(JiraField).where(JiraField.jira_field_id.in_(set(update.field_ids)))))
    if len(rows) != len(set(update.field_ids)):
        raise HTTPException(422, "One or more fields were not found")
    for row in rows:
        row.selected = update.selected
    db.commit()
    return {"updated_count": len(rows), "selected": update.selected}


@router.get("/metadata/fields/{field_id}/options")
def field_options(field_id: str, db: Db) -> dict[str, Any]:
    field = db.scalar(select(JiraField).where(JiraField.jira_field_id == field_id))
    if field is None:
        raise HTTPException(404, "Field not found")
    contexts = list(db.scalars(select(JiraFieldContext).where(JiraFieldContext.jira_field_id == field_id)))
    return {
        "field_id": field_id,
        "contexts": [
            {
                "context_id": x.context_id,
                "project_ids": x.project_ids_json,
                "issue_type_ids": x.issue_type_ids_json,
                "availability": x.availability,
                "message": x.message,
                "options": x.options_json,
                "fetched_at": x.fetched_at,
            }
            for x in contexts
        ],
        "sync_version": version(db),
    }


@router.get("/metadata/issue-types", response_model=ListEnvelope[IssueTypeOut])
def issue_types(db: Db) -> ListEnvelope[IssueTypeOut]:
    rows = list(db.scalars(select(JiraIssueType).order_by(JiraIssueType.hierarchy_level.desc(), JiraIssueType.name)))
    return ListEnvelope(items=[IssueTypeOut.model_validate(x) for x in rows], total_count=len(rows), sync_version=version(db))


@router.get("/metadata/statuses", response_model=ListEnvelope[StatusOut])
def statuses(db: Db) -> ListEnvelope[StatusOut]:
    rows = list(db.scalars(select(JiraStatus).order_by(JiraStatus.name)))
    return ListEnvelope(items=[StatusOut.model_validate(x) for x in rows], total_count=len(rows), sync_version=version(db))


@router.post("/admin/sync", dependencies=[Depends(require_admin)])
async def start_sync(request: SyncRequest, client: Annotated[JiraClient, Depends(jira_client)], db: Db) -> dict[str, Any]:
    if request.mode not in {"full", "incremental"}:
        raise HTTPException(422, "Sync mode must be 'full' or 'incremental'")
    try:
        run = await SyncService(db, client).run(request.mode, request.project_ids)
    except SyncBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return sync_run_dict(run)


def sync_run_dict(run: SyncRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "mode": run.mode,
        "projects": run.projects_json,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "fetched_count": run.fetched_count,
        "upserted_count": run.upserted_count,
        "missing_count": run.missing_count,
        "anomaly_count": run.anomaly_count,
        "watermark_before": run.watermark_before,
        "watermark_after": run.watermark_after,
        "error": run.error_json,
    }


@router.get("/admin/sync/runs")
def sync_runs(db: Db, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    rows = list(db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)))
    return {
        "items": [sync_run_dict(row) for row in rows],
        "next_cursor": None,
        "total_count": db.scalar(select(func.count()).select_from(SyncRun)) or 0,
        "sync_version": sync_version(db),
    }


@router.get("/admin/sync/status")
def sync_status(db: Db) -> dict[str, Any]:
    latest = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
    return {
        "running": bool(latest and latest.status == "running"),
        "latest": sync_run_dict(latest) if latest else None,
        "sync_version": sync_version(db),
    }


def issue_dict(issue: Issue, db: Session, include_fields: bool = False) -> dict[str, Any]:
    issue_type = db.scalar(select(JiraIssueType).where(JiraIssueType.jira_type_id == issue.issue_type_jira_id))
    status = db.scalar(select(JiraStatus).where(JiraStatus.jira_status_id == issue.status_jira_id))
    result: dict[str, Any] = {
        "jira_issue_id": issue.jira_issue_id,
        "issue_key": issue.issue_key,
        "project_id": issue.project_jira_id,
        "summary": issue.summary,
        "issue_type": {
            "id": issue.issue_type_jira_id,
            "name": issue_type.name if issue_type else None,
            "hierarchy_level": issue_type.hierarchy_level if issue_type else None,
        },
        "status": {
            "id": issue.status_jira_id,
            "name": status.name if status else None,
            "category_key": status.category_key if status else None,
        },
        "parent_jira_issue_id": issue.parent_jira_issue_id,
        "updated_at": issue.updated_at,
        "baseline_due_at": issue.baseline_due_at,
        "due_at": issue.due_at,
        "is_deleted_or_inaccessible": issue.is_deleted_or_inaccessible,
    }
    grid_config = db.scalar(select(GridConfig).where(GridConfig.project_jira_id == issue.project_jira_id))
    sprint_grid_config = db.scalar(select(SprintGridConfig).where(SprintGridConfig.project_jira_id == issue.project_jira_id))
    configured_fields = list(
        dict.fromkeys(
            (grid_config.optional_fields_json if grid_config else [])
            + (sprint_grid_config.optional_fields_json if sprint_grid_config else [])
        )
    )
    result["configured_fields"] = {field_id: issue.raw_fields_json.get(field_id) for field_id in configured_fields}
    if include_fields:
        values = list(
            db.scalars(
                select(IssueFieldValue)
                .where(IssueFieldValue.issue_id == issue.id)
                .order_by(IssueFieldValue.jira_field_id, IssueFieldValue.element_index)
            )
        )
        result["fields"] = [
            {
                "field_id": value.jira_field_id,
                "element_index": value.element_index,
                "value_type": value.value_type,
                "value": value.raw_value_json,
            }
            for value in values
        ]
        result["raw_fields"] = issue.raw_fields_json
        result["jira_url"] = f"{get_settings().jira_base_url}/browse/{issue.issue_key}"
    return result


@router.get("/issues")
def issues(
    db: Db,
    project_ids: Annotated[list[str] | None, Query()] = None,
    parent_id: str | None = None,
    filters: str | None = None,
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    query = select(Issue).where(Issue.is_deleted_or_inaccessible.is_(False))
    if project_ids:
        query = query.where(Issue.project_jira_id.in_(project_ids))
    if parent_id is not None:
        query = query.where(Issue.parent_jira_issue_id == parent_id)
    try:
        filter_ast = parsed_filters(filters)
        if filter_ast:
            query = query.where(AnalyticsService(db).compile_filter(filter_ast))
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(Issue.issue_key).offset(cursor).limit(limit)))
    return {
        "items": [issue_dict(row, db) for row in rows],
        "next_cursor": str(cursor + limit) if cursor + limit < total else None,
        "total_count": total,
        "sync_version": sync_version(db),
    }


@router.get("/issues/{jira_issue_id}")
def issue_detail(jira_issue_id: str, db: Db) -> dict[str, Any]:
    issue = db.scalar(select(Issue).where(Issue.jira_issue_id == jira_issue_id))
    if issue is None:
        raise HTTPException(404, "Issue not found")
    return issue_dict(issue, db, include_fields=True)


@router.get("/issues/{jira_issue_id}/children")
def issue_children(jira_issue_id: str, db: Db, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    parent = db.scalar(select(Issue).where(Issue.jira_issue_id == jira_issue_id))
    if parent is None:
        raise HTTPException(404, "Issue not found")
    query = select(Issue).where(Issue.parent_jira_issue_id == jira_issue_id, Issue.is_deleted_or_inaccessible.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(Issue.issue_key).offset(cursor).limit(limit)))
    return {
        "items": [issue_dict(row, db) for row in rows],
        "next_cursor": str(cursor + limit) if cursor + limit < total else None,
        "total_count": total,
        "sync_version": sync_version(db),
    }


@router.get("/hierarchy/roots")
def hierarchy_roots(
    db: Db, project_id: str | None = None, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    query = select(Issue).where(
        Issue.is_deleted_or_inaccessible.is_(False),
        or_(
            Issue.parent_jira_issue_id.is_(None),
            ~Issue.parent_jira_issue_id.in_(select(Issue.jira_issue_id).where(Issue.is_deleted_or_inaccessible.is_(False))),
        ),
    )
    if project_id:
        query = query.where(Issue.project_jira_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(Issue.issue_key).offset(cursor).limit(limit)))
    return {
        "items": [issue_dict(row, db) for row in rows],
        "next_cursor": str(cursor + limit) if cursor + limit < total else None,
        "total_count": total,
        "sync_version": sync_version(db),
    }


@router.get("/hierarchy/anomalies")
def hierarchy_anomalies(db: Db) -> dict[str, Any]:
    latest = sync_version(db)
    rows = list(db.scalars(select(HierarchyAnomaly).where(HierarchyAnomaly.sync_run_id == latest))) if latest else []
    return {
        "items": [{"issue_id": row.issue_id, "type": row.anomaly_type, "details": row.details_json} for row in rows],
        "next_cursor": None,
        "total_count": len(rows),
        "sync_version": latest,
    }


@router.get("/hierarchy/epics")
def hierarchy_epics(
    db: Db,
    project_ids: Annotated[list[str] | None, Query()] = None,
    filters: str | None = None,
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return epic ancestors for work items matching a metadata-driven filter."""
    matching_query = select(Issue).where(Issue.is_deleted_or_inaccessible.is_(False))
    scoped_query = select(Issue).where(Issue.is_deleted_or_inaccessible.is_(False))
    if project_ids:
        matching_query = matching_query.where(Issue.project_jira_id.in_(project_ids))
        scoped_query = scoped_query.where(Issue.project_jira_id.in_(project_ids))
    try:
        filter_ast = parsed_filters(filters)
        if filter_ast:
            matching_query = matching_query.where(AnalyticsService(db).compile_filter(filter_ast))
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    matching = list(db.scalars(matching_query))
    scoped = list(db.scalars(scoped_query))
    by_jira_id = {issue.jira_issue_id: issue for issue in scoped}
    hierarchy_levels = {issue_type.jira_type_id: issue_type.hierarchy_level for issue_type in db.scalars(select(JiraIssueType))}
    epic_ids: set[int] = set()
    for match in matching:
        current: Issue | None = match
        visited: set[str] = set()
        while current and current.jira_issue_id not in visited:
            visited.add(current.jira_issue_id)
            if hierarchy_levels.get(current.issue_type_jira_id or "") == 1:
                epic_ids.add(current.id)
                break
            current = by_jira_id.get(current.parent_jira_issue_id or "")

    epics = sorted((issue for issue in scoped if issue.id in epic_ids), key=lambda issue: issue.issue_key)
    page = epics[cursor : cursor + limit]
    return {
        "items": [issue_dict(issue, db) for issue in page],
        "next_cursor": str(cursor + limit) if cursor + limit < len(epics) else None,
        "total_count": len(epics),
        "matching_work_item_count": len(matching),
        "sync_version": sync_version(db),
    }


def parsed_filters(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "filters must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(422, "filters must be a JSON object")
    return parsed


@router.get("/portfolio/summary")
def portfolio_summary(
    db: Db,
    dashboard_id: int | None = None,
    project_ids: Annotated[list[str] | None, Query()] = None,
    filters: str | None = None,
) -> dict[str, Any]:
    filter_ast = parsed_filters(filters)
    if dashboard_id:
        dashboard = db.get(DashboardConfig, dashboard_id)
        if dashboard is None:
            raise HTTPException(404, "Dashboard not found")
        project_ids = project_ids or dashboard.scope_json.get("project_ids")
        filter_ast = filter_ast or dashboard.filters_json
    try:
        return AnalyticsService(db).summary(project_ids, filter_ast)
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analytics/group-by")
def analytics_group_by(request: GroupByRequest, db: Db) -> dict[str, Any]:
    try:
        if request.aggregation != "count":
            return AnalyticsService(db).numeric_aggregate(request.field_id, request.aggregation, request.project_ids, request.filters)
        return AnalyticsService(db).group_by(request.field_id, request.project_ids, request.filters)
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analytics/card-groups")
def analytics_card_groups(request: CardSummaryRequest, db: Db) -> dict[str, Any]:
    try:
        service = AnalyticsService(db)
        grouped = service.group_by(request.field_id, request.project_ids, request.filters)
        for group in grouped["groups"]:
            leaf_filter = {
                "field_id": request.field_id,
                "operator": "is_null" if group["value"] is None else "eq",
                "value": True if group["value"] is None else group["value"],
            }
            scoped_filter = {"and": [request.filters, leaf_filter]} if request.filters else leaf_filter
            group.update(service.card_summary(request.project_ids, scoped_filter, request.next_field_id))
        return grouped
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analytics/timeseries")
def analytics_timeseries() -> None:
    raise HTTPException(501, "Timeseries requires report snapshots")


def metric_dict(row: MetricDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "metric_type": row.metric_type,
        "numerator_filter": row.numerator_filter_json,
        "denominator_filter": row.denominator_filter_json,
        "aggregation": row.aggregation_json,
        "field_id": row.field_id,
        "scope": row.scope_json,
        "updated_at": row.updated_at,
    }


def validate_metric(config: MetricConfigIn, db: Session) -> None:
    if config.metric_type not in {"ratio", "count", "numeric"}:
        raise HTTPException(422, "metric_type must be ratio, count, or numeric")
    service = AnalyticsService(db)
    try:
        if config.numerator_filter:
            service.compile_filter(config.numerator_filter)
        if config.denominator_filter:
            service.compile_filter(config.denominator_filter)
    except FilterValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if config.field_id and config.field_id not in {"due_at", "updated_at"}:
        exists_field = db.scalar(select(JiraField.id).where(JiraField.jira_field_id == config.field_id))
        if not exists_field:
            raise HTTPException(422, "Unknown metric field_id")


@router.get("/metrics")
def metrics(db: Db) -> dict[str, Any]:
    rows = list(db.scalars(select(MetricDefinition).order_by(MetricDefinition.name)))
    return {"items": [metric_dict(row) for row in rows], "next_cursor": None, "total_count": len(rows), "sync_version": sync_version(db)}


@router.post("/metrics", dependencies=[Depends(require_admin)])
def create_metric(config: MetricConfigIn, db: Db) -> dict[str, Any]:
    validate_metric(config, db)
    row = MetricDefinition(
        name=config.name,
        metric_type=config.metric_type,
        numerator_filter_json=config.numerator_filter,
        denominator_filter_json=config.denominator_filter,
        aggregation_json=config.aggregation,
        field_id=config.field_id,
        scope_json=config.scope,
    )
    db.add(row)
    db.commit()
    return metric_dict(row)


@router.put("/metrics/{metric_id}", dependencies=[Depends(require_admin)])
def update_metric(metric_id: int, config: MetricConfigIn, db: Db) -> dict[str, Any]:
    row = db.get(MetricDefinition, metric_id)
    if row is None:
        raise HTTPException(404, "Metric not found")
    validate_metric(config, db)
    row.name, row.metric_type = config.name, config.metric_type
    row.numerator_filter_json, row.denominator_filter_json = config.numerator_filter, config.denominator_filter
    row.aggregation_json, row.field_id, row.scope_json = config.aggregation, config.field_id, config.scope
    db.commit()
    return metric_dict(row)


@router.delete("/metrics/{metric_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_metric(metric_id: int, db: Db) -> None:
    row = db.get(MetricDefinition, metric_id)
    if row is None:
        raise HTTPException(404, "Metric not found")
    db.delete(row)
    db.commit()


def dashboard_dict(row: DashboardConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "scope": row.scope_json,
        "layout": row.layout_json,
        "filters": row.filters_json,
        "shared": row.shared,
        "version": row.version,
        "updated_at": row.updated_at,
    }


def validate_dashboard(config: DashboardConfigIn, db: Session) -> None:
    if config.filters:
        try:
            AnalyticsService(db).compile_filter(config.filters)
        except FilterValidationError as exc:
            raise HTTPException(422, str(exc)) from exc


@router.get("/dashboards")
def dashboards(db: Db) -> dict[str, Any]:
    rows = list(db.scalars(select(DashboardConfig).order_by(DashboardConfig.name)))
    return {"items": [dashboard_dict(row) for row in rows], "next_cursor": None, "total_count": len(rows), "sync_version": sync_version(db)}


@router.post("/dashboards", dependencies=[Depends(require_admin)])
def create_dashboard(config: DashboardConfigIn, db: Db) -> dict[str, Any]:
    validate_dashboard(config, db)
    row = DashboardConfig(
        name=config.name,
        description=config.description,
        scope_json=config.scope,
        layout_json=config.layout,
        filters_json=config.filters,
        shared=config.shared,
    )
    db.add(row)
    db.commit()
    return dashboard_dict(row)


@router.get("/dashboards/{dashboard_id}")
def dashboard(dashboard_id: int, db: Db) -> dict[str, Any]:
    row = db.get(DashboardConfig, dashboard_id)
    if row is None:
        raise HTTPException(404, "Dashboard not found")
    return dashboard_dict(row)


@router.put("/dashboards/{dashboard_id}", dependencies=[Depends(require_admin)])
def update_dashboard(dashboard_id: int, config: DashboardConfigIn, db: Db) -> dict[str, Any]:
    row = db.get(DashboardConfig, dashboard_id)
    if row is None:
        raise HTTPException(404, "Dashboard not found")
    validate_dashboard(config, db)
    row.name, row.description, row.scope_json = config.name, config.description, config.scope
    row.layout_json, row.filters_json, row.shared = config.layout, config.filters, config.shared
    row.version += 1
    db.commit()
    return dashboard_dict(row)


@router.delete("/dashboards/{dashboard_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_dashboard(dashboard_id: int, db: Db) -> None:
    row = db.get(DashboardConfig, dashboard_id)
    if row is None:
        raise HTTPException(404, "Dashboard not found")
    db.delete(row)
    db.commit()
