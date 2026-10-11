# Architecture and Technical Design

## Stack
Frontend: React 19, TypeScript, Vite, React Router, TanStack Query, TanStack Table (expandable server-side tree), Apache ECharts, React Hook Form, Zod, accessible component library. Backend: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, APScheduler or dedicated sync worker, pytest. DB: SQLite WAL for single deployment. Docker Compose optional.

## Logical components
- JiraClient: authenticated REST API calls, pagination, 429 Retry-After, backoff, timeouts, correlation IDs, bounded concurrency.
- MetadataService: discover fields, contexts/options and issue types/statuses; version metadata and identify changes.
- SyncService: full bootstrap, incremental overlap window, idempotent upserts, reconciliation of deleted/inaccessible issues, refresh hierarchy and field values; run one writer at a time.
- HierarchyService: materialized parent links, cycle detection, missing parent handling, descendant queries, lazy children.
- MetricsService: typed aggregations over selected scopes and field definitions; separate filtering of ancestor visibility from descendant aggregation.
- ConfigService: validated field references, layouts, metric definitions, saved views and audit.
- API: read endpoints plus authenticated admin configuration/sync endpoints.

## Jira integration details
Use Atlassian Jira Cloud REST API v3. Use enhanced JQL search (`POST /rest/api/3/search/jql` or documented supported variant) with `nextPageToken`, requested fields and bounded pages; do not use removed legacy offset search as the only implementation. Some Jira endpoints are paginated independently. Issue `fields.parent` is authoritative for standard parent-child nesting when returned. For hierarchy above Epic, inspect site/project hierarchy metadata or document limitations. Do not infer story→task nesting merely from issue types. Issue links are dependencies, not parent-child relationships. Include `updated` and stable issue IDs; keys may change. Capture deleted/inaccessible issues via periodic full reconciliation (incremental JQL alone cannot detect deletion). Query with an overlap window to tolerate updates during sync, deduplicate by issue ID, and preserve last-good snapshot on failure.

## Security
Service account uses minimum Jira read scopes and authorized projects. Secrets from env/secret manager; never store plain API token in SQLite. Authentication for local app required before deployment (proxy SSO or secure session/JWT); role separation executive/editor/admin. CSRF protection for cookie auth, CORS allowlist, HTTPS behind reverse proxy, request validation, audit config edits. Never bypass Jira access controls: service-account visibility may exceed end-user visibility, so restrict project access by app role or implement per-user Jira auth for strict parity.

## Performance
Use normalized typed field-value indexes for filtering/grouping plus raw JSON for fidelity. Avoid loading all issues into browser. Paginate table and lazy-load children; cache aggregate queries keyed by config/filter/sync version. Build indexes on project, parent, status, updated, field ID/value. SQLite suits one backend instance and one sync writer; move to PostgreSQL for multi-instance concurrency or heavier write/reporting loads. Do not put SQLite on shared network storage for multi-node active-active operation.

## Sync phases
1. Read metadata and selected project scope.
2. Fetch pages into staging tables/batch transaction, tracking watermark and sync ID.
3. Validate, upsert issue identities/fields, resolve parents and orphans.
4. Recompute/materialize aggregate dependencies and atomically publish completed sync version.
5. Reconcile deletions/inaccessibility in scheduled full scan; retain tombstones/audit where needed.
6. Expose sync run statistics, last-success time and errors.
