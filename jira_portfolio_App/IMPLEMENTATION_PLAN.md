# Codex Build Plan and Acceptance Checklist

## Phase 0 — Scaffold
Monorepo `backend/`, `frontend/`, `tests/`, `docs/`; environment template; Docker Compose optional; make/dev scripts; CI for lint, typing and tests. Implement SQLite migrations, structured logging and health endpoints.

## Phase 1 — Jira metadata and connectivity
Jira client, auth validation, project catalog, field catalog, issue types/statuses, field contexts/options with permissions-aware fallbacks. Admin UI to select projects and fields. Mock tests for 401/403/429, paging and renamed custom fields.

## Phase 2 — Sync and hierarchy
Bootstrap and incremental enhanced-JQL search; durable checkpoint; raw+typed values; parent resolution, cross-project handling, orphan/cycle detection, tombstone reconciliation, sync UI. Fixtures for 4-level nesting AND nonstandard nesting (Task under Epic, Story under Epic, Task root). Verify no duplicate issue counting.

## Phase 3 — Executive analytics
Generic metadata-driven filters, group-bys and metric definitions; KPI summaries with denominators and null counts; status distribution; overdue; dynamic custom-field breakdowns; dashboard persistence. Test numeric, categorical, multi-select and date field semantics.

## Phase 4 — React UI
Overview, projects, expandable lazy hierarchy grid, issue drawer, charts with cross-filter, dashboard builder, field catalog, sync monitor. Responsive, keyboard-accessible. Add real demo mode using explicit fixtures and banner, not silent fake Jira data.

## Phase 5 — Hardening
Role/project authorization, config audit, stale-data notices, performance profiling at 10k+ issues, API contract tests, end-to-end browser tests, README, deployment notes and backup/restore.

## Definition of done
- From `.env` and setup instructions, local stack starts successfully.
- Admin connects Jira and selects a project without changing source code.
- Newly added Jira custom field appears after metadata refresh and can be used as grid column, filter and grouping where type supports it.
- Executive can drill project → Epic → descendants → leaf with accurate parent relationships.
- Every metric has a documented formula and visible scope/freshness.
- Changing Jira issue parent, status or custom field is reflected after sync.
- Failure during sync preserves prior published view.
- Unit, integration and browser smoke tests pass.

## First Codex task
Implement Phase 0 and Phase 1 end to end. Read all markdown files first, propose a short implementation checklist, create the working code, migrations, mock tests and README, run checks, then report actual files and test outcomes. Do not start Phase 2 until Phase 1 is verifiably functional.
