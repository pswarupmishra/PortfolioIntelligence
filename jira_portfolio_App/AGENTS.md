# Instructions — Jira Executive Portfolio Intelligence

Read `PRD.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `API_CONTRACT.md`, and `IMPLEMENTATION_PLAN.md` before implementing. Build production-minded, testable software in small vertical slices. Do not fabricate Jira data or assume custom-field IDs, hierarchy levels, or status names.

## Non-negotiable principles
- Jira Cloud REST API v3 is the authoritative read-only source for MVP. No Jira writes.
- React + TypeScript + Vite frontend; FastAPI + Python backend; SQLite with SQLAlchemy 2 and Alembic migrations.
- Discover Jira projects, fields, contexts/options where accessible, issue types, statuses and issue hierarchy dynamically. Store raw Jira field IDs and typed normalized values. Never hardcode `customfield_XXXXX`.
- Use Jira's current enhanced JQL search endpoint `/rest/api/3/search/jql` with pagination via `nextPageToken`; use `/rest/api/3/field`, `/rest/api/3/project/search`, `/rest/api/3/issuetype`, and other documented endpoints as needed. Account for API permissions, rate limits, retries, and field pagination. Verify current Atlassian API documentation before relying on an endpoint.
- Resolve hierarchy using `parent` links and Jira project configuration; do not assume every project has all four levels or that all Tasks are children of Stories. Epic/Story/Task/Sub-task is a target display model, not a universal Jira invariant. Preserve actual parent relationships and expose orphans/cross-project links.
- Store application-specific dashboard layouts, metric definitions, field mappings, filters, sync logs and permissions locally. Jira owns issue data.
- Aggregate distinct issues, not repeated descendant counts. Specify denominator, rollup rule, null handling, and status mapping for every metric. Never imply native Jira progress semantics without configuration.
- Protect credentials in environment variables/server-side secret storage; never expose Jira API tokens in React, logs, or API responses.
- Use UTC in storage, user timezone in UI. SQLite WAL, foreign keys, single-writer aware sync, transactional upserts and indexed queries.
- Implement unit/integration tests with mocked Jira responses, including pagination, changed fields, deleted/inaccessible issues, parent changes, missing fields, cycles, and rate limits.
- Keep README updated with exact local setup and run commands. Include `.env.example`, sample fixture data explicitly labeled demo, and a one-command developer startup if practical.

## Delivery workflow
1. Scaffold backend/frontend and tests.
2. Implement Jira connection test and metadata discovery.
3. Implement initial/incremental synchronization and hierarchy integrity checks.
4. Implement configurable metrics/filter/query APIs.
5. Implement executive dashboard and recursive drill-down UI.
6. Implement configuration console, observability, security and acceptance tests.

At each step run tests, lint/typecheck, document any limitations, and avoid replacing functional code with placeholders.
