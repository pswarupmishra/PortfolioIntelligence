"""Independent, append-only SQLite store for portfolio delivery snapshots."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Issue, JiraProject, JiraStatus

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "portfolio_intelligence_history.db"


def database_path() -> Path:
    return Path(os.environ.get("INTELLIGENCE_DB_PATH", str(DEFAULT_PATH))).expanduser().resolve()


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS issue_snapshots (
      snapshot_date TEXT NOT NULL,
      jira_issue_id TEXT NOT NULL,
      project_jira_id TEXT NOT NULL,
      issue_key TEXT NOT NULL,
      status_category TEXT NOT NULL,
      created_at TEXT,
      resolved_at TEXT,
      due_at TEXT,
      updated_at TEXT,
      captured_at TEXT NOT NULL,
      PRIMARY KEY(snapshot_date, jira_issue_id)
    );
    CREATE INDEX IF NOT EXISTS ix_snapshot_project_date
      ON issue_snapshots(project_jira_id, snapshot_date);
    CREATE TABLE IF NOT EXISTS capture_runs (
      sync_run_id INTEGER PRIMARY KEY,
      captured_at TEXT NOT NULL,
      snapshot_date TEXT NOT NULL,
      issue_count INTEGER NOT NULL
    );
    """)
    return conn


def capture(db: Session, sync_run_id: int, project_ids: list[str]) -> int:
    """Capture current state after successful sync. Idempotent per run; one state per issue/day.

    For partial syncs, preserves other projects' last captured states. Historical values
    are observed snapshots, not reconstructed Jira changelog history.
    """
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    rows = db.execute(
        select(Issue.jira_issue_id, Issue.project_jira_id, Issue.issue_key,
               JiraStatus.category_key, Issue.created_at, Issue.resolved_at,
               Issue.due_at, Issue.updated_at)
        .outerjoin(JiraStatus, Issue.status_jira_id == JiraStatus.jira_status_id)
        .where(Issue.project_jira_id.in_(project_ids))
        .where(Issue.is_deleted_or_inaccessible.is_(False))
    ).all()
    def iso(v):
        return v.isoformat() if v is not None else None
    with connect() as conn:
        if conn.execute("SELECT 1 FROM capture_runs WHERE sync_run_id=?", (sync_run_id,)).fetchone():
            return 0
        conn.executemany("""
          INSERT INTO issue_snapshots (
            snapshot_date, jira_issue_id, project_jira_id, issue_key, status_category,
            created_at, resolved_at, due_at, updated_at, captured_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(snapshot_date, jira_issue_id) DO UPDATE SET
            project_jira_id=excluded.project_jira_id,
            issue_key=excluded.issue_key,
            status_category=excluded.status_category,
            created_at=excluded.created_at,
            resolved_at=excluded.resolved_at,
            due_at=excluded.due_at,
            updated_at=excluded.updated_at,
            captured_at=excluded.captured_at
        """, [(day, issue_id, project_id, key, (category or "unknown").lower(),
                iso(created), iso(resolved), iso(due), iso(updated), now.isoformat())
               for issue_id, project_id, key, category, created, resolved, due, updated in rows])
        conn.execute("INSERT INTO capture_runs VALUES (?, ?, ?, ?)",
                     (sync_run_id, now.isoformat(), day, len(rows)))
    return len(rows)


def report(project_id: str | None = None, days: int = 90) -> dict:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    with connect() as conn:
        # All chart values come from real snapshots; no synthetic trend or backfill.
        where = "snapshot_date >= ?"
        args: list = [cutoff]
        if project_id:
            where += " AND project_jira_id = ?"
            args.append(project_id)
        rows = conn.execute(f"""
          SELECT snapshot_date,
            COUNT(*) total,
            SUM(CASE WHEN status_category = 'done' THEN 1 ELSE 0 END) done,
            SUM(CASE WHEN status_category = 'indeterminate' THEN 1 ELSE 0 END) in_progress,
            SUM(CASE WHEN status_category NOT IN ('done', 'indeterminate') THEN 1 ELSE 0 END) to_do,
            SUM(CASE WHEN status_category != 'done'
                  AND due_at IS NOT NULL AND substr(due_at,1,10) < snapshot_date
                  THEN 1 ELSE 0 END) overdue,
            SUM(CASE WHEN status_category != 'done' AND updated_at IS NOT NULL
                  AND julianday(snapshot_date) - julianday(substr(updated_at,1,10)) >= 30
                  THEN 1 ELSE 0 END) stale_30d
          FROM issue_snapshots WHERE {where}
          GROUP BY snapshot_date ORDER BY snapshot_date
        """, args).fetchall()
        history = [dict(row) for row in rows]
        for row in history:
            row["completion_pct"] = round(100 * row["done"] / row["total"], 1) if row["total"] else 0
        latest = history[-1] if history else None
        return {
          "source": "observed_snapshots",
          "project_id": project_id,
          "days": days,
          "points": history,
          "latest": latest,
          "first_snapshot": history[0]["snapshot_date"] if history else None,
          "last_snapshot": history[-1]["snapshot_date"] if history else None,
          "message": None if history else "No historical snapshots yet. Run a Jira synchronization to capture the first observation.",
          "caveat": "Daily observed state only. This does not reconstruct historical Jira status changes or sprint commitments."
        }
