# Jira Executive Portfolio Intelligence

Phase 0 through Phase 3 provide a runnable React/FastAPI application for securely connecting Jira Cloud, discovering metadata, synchronizing selected projects, preserving Jira's actual issue hierarchy, and calculating configurable portfolio analytics without source-code assumptions.

## What is implemented

- FastAPI API with structured request logs, typed Jira errors, CORS, liveness/readiness checks, and OpenAPI at `/docs`.
- Read-only Jira Cloud REST v3 client using server-side Basic auth (email + API token), timeouts, correlation IDs, bounded retries, `Retry-After`, pagination, and bounded context discovery concurrency.
- Dynamic catalogs for projects, fields, custom-field contexts/options, issue types, statuses, and Jira hierarchy levels where Jira provides them.
- Permission-aware context/option discovery: 403 responses are recorded as unavailable metadata rather than replaced with guesses.
- SQLite persistence through SQLAlchemy 2 and Alembic. Connections store only an environment credential reference—not the API token. SQLite enables WAL and foreign keys.
- React configuration console for connection checks, metadata refresh, project scope, searchable fields, and field selection.
- Full and incremental issue synchronization through Jira's enhanced `POST /rest/api/3/search/jql` endpoint and `nextPageToken` pagination.
- Durable UTC watermarks with a five-minute incremental overlap, idempotent Jira-ID upserts, and full-sync tombstone reconciliation for deleted or inaccessible issues.
- Raw Jira field payloads plus normalized scalar, option, user, date, number, boolean, null, and multivalue elements.
- Parent relationships resolved by stable Jira issue ID, including explicit missing/external parents and cycle detection—without assuming issue-type names or hierarchy depth.
- Sync monitor with full/incremental controls, run statistics, hierarchy roots/orphans, and anomaly counts.
- Validated metadata-driven filter AST with `and/or/not` plus `eq`, `ne`, `in`, `not_in`, `is_null`, `contains`, `gte`, `lte`, and `between` where field types support them.
- Distinct-issue group-by for core and custom fields, explicit non-additive warnings for multiselect fields, and numeric `sum/avg/min/max` with excluded-null counts.
- Portfolio KPIs for total work, leaf completion, overdue, and unassigned items with visible numerators, denominators, null counts, warnings, freshness, and sync version.
- Due-date changelog synchronization for Jira's standard `duedate` field, preserving the first assigned date as an immutable baseline. Card summaries distinguish baseline delayed, revised on-track, and revised delayed open leaf tasks.
- Persisted metric definitions and dashboard configurations with field/filter validation and CRUD APIs.
- Local SQLite user management with PBKDF2-SHA256 password hashing, 12-hour bearer sessions, administrator/user roles, and per-screen navigation access.
- Project-scoped field catalogs using available Jira field contexts plus observed synchronized project fields; permission-limited contexts are not treated as globally applicable.
- Project and field filters with filtered Include-all/Exclude-all synchronization controls.
- Persistent application-wide Default, Comfortable, and Large text modes.
- Clickable Overview project snapshots that open WBS with the selected Jira project.
- Mocked tests for paging, 401/403, 429 retry/exhaustion, metadata persistence, renamed custom fields, and basic API authorization/health.

Historical trend snapshots and Phase 4's full interactive dashboard builder are intentionally not included yet.

## Prerequisites

- Python 3.10+ (3.12 recommended)
- Node.js 20+ and npm
- A Jira Cloud service account with the minimum required read permissions

The backend uses these read-only Jira endpoints: `/rest/api/3/myself`, `/project/search`, `/field`, `/issuetype`, `/status`, and custom-field context/option endpoints. Jira may require administrative permission for some field metadata; the UI/API surfaces that limitation.
Issue synchronization also uses `POST /rest/api/3/changelog/bulkfetch`, filtered to the standard `duedate` field, to derive baseline-versus-revised schedule metrics.

## Local setup

For a complete first-time installation walkthrough—including `.env`, Jira credentials, SQLite creation, migrations, startup, first sync, updates, and troubleshooting—see [LOCAL_SETUP.md](LOCAL_SETUP.md).

```bash
cp .env.example .env
# Edit .env with your Jira Cloud URL, service-account email, and API token.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cd frontend && npm install && cd ..
make migrate
```

Never commit `.env`. `JIRA_API_TOKEN` is read only by FastAPI and is never returned by the API or bundled into the frontend.

Start both services with:

```bash
make dev
```

Then open `http://localhost:5173`. Sign in initially as `admin` with password `Pass@1237`, then change that password in User management. The API is at `http://localhost:8000`, with Swagger UI at `http://localhost:8000/docs`.

Alternatively run `make backend` and `make frontend` in separate terminals. The development UI sends `X-App-Role: admin`; production deployment must replace this Phase 1 role boundary with trusted proxy/SSO authentication as described in `ARCHITECTURE.md`.

## Checks

```bash
make test
make lint
cd frontend && npm run build
```

Run only the backend tests with `cd backend && pytest`. Tests use mocked Jira responses and do not need Jira credentials.

## API highlights

- `POST /api/v1/jira/test-connection`
- `POST /api/v1/admin/metadata/refresh`
- `GET /api/v1/jira/projects`
- `GET /api/v1/metadata/fields?project_id=&issue_type_id=&search=`
- `GET /api/v1/metadata/fields/{field_id}/options`
- `GET /api/v1/metadata/issue-types`
- `GET /api/v1/metadata/statuses`
- `PUT /api/v1/admin/projects/{jira_project_id}` and `PUT /api/v1/admin/fields/{jira_field_id}` for local selection
- `POST /api/v1/admin/sync` with `{mode: "full"|"incremental", project_ids?: [...]}`
- `GET /api/v1/admin/sync/status` and `/api/v1/admin/sync/runs`
- `GET /api/v1/issues`, `/api/v1/issues/{jira_issue_id}`, and `/api/v1/issues/{jira_issue_id}/children`
- `GET /api/v1/hierarchy/roots` and `/api/v1/hierarchy/anomalies`
- `GET /api/v1/portfolio/summary?project_ids=&filters=`
- `POST /api/v1/analytics/group-by` for distinct counts and numeric aggregation
- `POST /api/v1/analytics/timeseries` explicitly returns `501` until snapshots are enabled
- `GET/POST/PUT/DELETE /api/v1/metrics` and `/api/v1/dashboards`
- `GET /api/v1/health/live` and `/api/v1/health/ready`

The frontend authenticates with a local session token. Administrator endpoints verify the signed-in user's role. Metadata list responses use the documented `{items,next_cursor,total_count,sync_version}` envelope.

## Known Phase 1 limitations

- Atlassian permissions can hide field contexts/options; each affected field records an explicit availability state.
- Jira does not expose every hierarchy configuration through one universally available endpoint. The application stores Jira-provided `hierarchyLevel` values without assuming names or depth; further project-specific hierarchy validation belongs to Phase 2.
- Local header-based role gating is a development boundary, not deployable authentication. Configure SSO/proxy authentication before exposing the service.
- Metadata refresh and issue sync currently run in the request lifecycle. A process-local lock enforces one sync writer; production multi-process deployment should move jobs to a dedicated worker/queue.
- Full sync is the reconciliation boundary that marks unseen issues deleted/inaccessible. Incremental sync never tombstones unseen issues.
