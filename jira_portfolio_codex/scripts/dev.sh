#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -d "$PROJECT_DIR/.venv/bin" ]]; then
  export PATH="$PROJECT_DIR/.venv/bin:$PATH"
fi
trap 'kill 0' EXIT
(cd "$PROJECT_DIR/backend" && alembic upgrade head && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
(cd "$PROJECT_DIR/frontend" && npm run dev -- --host 127.0.0.1) &
wait
