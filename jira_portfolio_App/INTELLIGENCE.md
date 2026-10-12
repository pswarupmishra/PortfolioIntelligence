# Portfolio Time-Series Intelligence

Separate SQLite storage: `INTELLIGENCE_DB_PATH` (default `jira_portfolio_App/data/portfolio_intelligence_history.db`). Do not commit the SQLite database or its WAL/SHM files.

## Data capture
After each successful Jira sync, the application copies current issue states into `issue_snapshots` (one observation per issue/day) and records `capture_runs`. The intelligence store is independent of Alembic and the application database. A failed intelligence capture does not roll back the successful Jira sync; the API sync handler logs a warning. Re-run the sync to retry capture. Snapshots begin at deployment; no historical status data is invented.

## UI
Sidebar **Intelligence** opens the 30/60/90-day dashboard. Charts show completion, total backlog, Done/In Progress/To Do, overdue and stale work. The scope selector supports all active projects or one active project. With fewer than two observation dates, the UI explicitly states that trends are not established.

## API
`GET /api/v1/intelligence/trends?days=90&project_id=...` requires authentication and Intelligence screen permission. The endpoint returns recorded observations, not generated demo data.

## Caveats
Snapshots represent end-of-sync observed state, not a full Jira changelog. A partial project sync updates only selected projects on the day; cross-project trend points should be treated as incomplete until all projects have been captured. Full historical sprint burn-down, scope-entry events, baseline variance and predictive estimates require additional event ingestion. At present percent-complete uses equal issue counts (not effort weighting). Back up both SQLite databases including committed WAL data using SQLite-aware backup procedures.
