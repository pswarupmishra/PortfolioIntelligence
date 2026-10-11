# FastAPI API Contract (v1)

Return consistent envelopes for paginated lists: `{items, next_cursor, total_count?, sync_version}`. Return typed errors `{code,message,details?,request_id}`. Enforce role checks and pagination bounds. Generate OpenAPI and TypeScript client types.

## Connection and metadata
- `POST /api/v1/jira/test-connection` (admin): validate credentials without echoing secrets.
- `GET /api/v1/jira/projects` (authorized scope).
- `POST /api/v1/admin/metadata/refresh` (admin).
- `GET /api/v1/metadata/fields?project_id=&issue_type_id=&search=`.
- `PUT /api/v1/admin/fields` (admin) body `{field_ids,selected}` for filtered bulk inclusion/exclusion.
- `GET /api/v1/metadata/fields/{field_id}/options`.
- `GET /api/v1/metadata/issue-types`, `GET /api/v1/metadata/statuses`.

## Portfolio and hierarchy
- `GET /api/v1/portfolio/summary?dashboard_id=&project_ids=&filters=` — metric values, denominators, freshness.
- `POST /api/v1/analytics/group-by` body `{scope,filters,field_id,aggregation,metric_id?}`.
- `POST /api/v1/analytics/timeseries` (if snapshots available; otherwise explicitly 501).
- `GET /api/v1/issues?project_ids=&parent_id=&cursor=&limit=&sort=&filters=` — paginated rows.
- `GET /api/v1/issues/{issue_id}` — full field mapping and Jira URL.
- `GET /api/v1/issues/{issue_id}/children?cursor=&limit=` — direct children only.
- `GET /api/v1/issues/{issue_id}/rollup?metric_ids=` — deduplicated descendant metrics.
- `GET /api/v1/hierarchy/roots?scope=&cursor=&limit=` — roots and flagged orphans.
- `GET /api/v1/hierarchy/anomalies` — cycles, missing parents, unexpected levels.

## Configuration and operations
- `POST /api/v1/auth/login`; `GET /api/v1/auth/me`; `POST /api/v1/auth/logout`.
- `GET/POST /api/v1/admin/users`; `PUT/DELETE /api/v1/admin/users/{id}` (admin) for local accounts and screen permissions.
- `GET/POST /api/v1/dashboards`; `GET/PUT/DELETE /api/v1/dashboards/{id}`.
- `GET/POST /api/v1/metrics`; `GET/PUT/DELETE /api/v1/metrics/{id}`.
- `POST /api/v1/admin/sync` (admin, async enqueue).
- `GET /api/v1/admin/sync/runs`, `GET /api/v1/admin/sync/status`.
- `GET /api/v1/me`, `GET /api/v1/health/live`, `GET /api/v1/health/ready`.

## Filters
Define a validated JSON filter AST with `and/or/not` and operators `eq,ne,in,not_in,is_null,contains,gte,lte,between` where supported by field type. Reject unknown fields, unsupported operators and unsafe SQL fragments. Field selection is metadata-driven. Restrict group-by to typed scalar values or explode multiselect explicitly with labels explaining non-additive totals.

## Response example
`{ "metric_id": "leaf_completion", "value": 0.68, "numerator": 34, "denominator": 50, "unit": "ratio", "as_of": "2026-10-10T12:00:00Z", "sync_version": 14, "warnings": [] }`
