# Product Requirements — Jira Executive Portfolio Intelligence

## Purpose
Build a configurable C-level portfolio reporting application over existing Jira Cloud projects, preserving Jira as the system of record. The primary workflow is portfolio → project → epic → story/task → task/sub-task → leaf issue, showing configurable Jira custom-field attributes and rollup analytics at every level.

## Personas
- Executive: cross-project portfolio health, trends, exceptions, ownership, milestones.
- Portfolio manager: configure scorecards, dimensions, filters, drilldowns and saved views.
- Project lead: inspect hierarchy, blockers, issue details and data-quality exceptions.
- Administrator: configure Jira connectivity, project scope, sync and access controls.

## Functional scope (MVP)
1. Connection setup/test for Jira Cloud base URL, service account email, API token, with server-only credentials.
2. Project selection and metadata discovery: issue types, statuses, field catalog, field types, custom fields, applicable contexts/options where permitted, and per-project issue-type applicability. Surface unsupported metadata access rather than guessing.
3. Metadata explorer showing field ID, display name, schema/type, allowed values when available, example observed values, availability and last refresh.
4. Configuration wizard to choose projects, visible attributes, dashboard dimensions, metric definitions, issue display columns, filters and sort order; no code changes.
5. Synchronize issues, parent relationships, fields and changelog-derived facts only where needed and permitted; initial full load then incremental refresh; manual refresh and sync health.
6. Recursive, virtualized expandable tree/grid with configurable columns and row details, direct Jira link, search and filters; supports varying depths, cross-project parents, missing ancestors and unattached items.
7. Portfolio/project/epic KPI tiles: issue counts by type/status, configurable completion, overdue, at-risk, unassigned, and breakdown by arbitrary selected Jira fields. Status categories are fallback only; user-defined status mapping takes precedence.
8. Interactive chart selection filters the issue grid; breadcrumb drilldown; issue details panel shows raw Jira field name/value mapping and inherited context only when explicitly defined.
9. Save named dashboard configurations and share by app role; allow multiple executive views for different projects.
10. Audit config edits and report data freshness.

## Advanced features (post-MVP)
- Historical trend snapshots, baseline vs current, change-history cycle-time analysis, workload/capacity, Jira issue links/dependencies, scheduled reports, SSO/AD, PostgreSQL migration, row-level access, Jira webhooks, export to Excel/PDF.

## Executive metric rules
- Total work items = count distinct issue IDs in configured scope.
- Completion % = configured numerator / configured denominator; default numerator statusCategory=Done and denominator all included leaf issues, excluding canceled issues only if configured. Label as leaf completion, not percent effort.
- Overdue = due date before local reporting date AND not mapped Done; missing due dates excluded and counted separately.
- Epic health = configurable aggregation of descendants; missing descendants, null dates, and unmapped statuses flagged.
- Distinguish direct-child count, unique-descendant count, and leaf count.
- Cross-project scope and duplicate ancestry must not double-count an issue.
- Numeric fields may aggregate SUM/AVG/MIN/MAX with explicit null treatment; categorical fields support counts and distribution; dates support earliest/latest/overdue; user fields support owner groupings.
- Percentages show denominator and as-of sync timestamp; never invent weights or business meaning.

## UX
Clean executive-friendly, accessible light-theme interface with large readable typography and responsive layout. Pages: Overview, Projects, Hierarchy, Analytics, Dashboard Builder, Field Catalog, Sync Monitor, Settings. Overview: scope/date/freshness banner, KPI cards, status distribution, dimension breakdown, project table and exception list. Hierarchy: expandable tree, sticky key/summary columns, column picker, quick filters, breadcrumb and issue drawer. Provide empty/error/loading states and keyboard navigation.

## Nonfunctional acceptance
- A user can add a new Jira custom field and expose it through metadata refresh + dashboard configuration without deploying code.
- A parent change in Jira appears correctly after synchronization.
- Pagination retrieves all eligible issues, not just the first page.
- 10k issue fixture is usable with server-side pagination and tree lazy-loading; define and measure local performance targets rather than claiming untested SLAs.
- Sync errors do not corrupt last good reporting data; UI displays stale-data warning.
- Credentials never leave backend; Jira permissions respected; no write-back in MVP.
