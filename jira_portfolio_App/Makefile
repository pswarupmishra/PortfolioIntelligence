.PHONY: install migrate backend frontend dev test lint

install:
	python3 -m pip install -e './backend[dev]'
	cd frontend && npm install

migrate:
	cd backend && alembic upgrade head

backend:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev -- --host 127.0.0.1

dev:
	./scripts/dev.sh

test:
	cd backend && pytest
	cd frontend && npm run test -- --run

lint:
	cd backend && ruff check . && mypy app
	cd frontend && npm run lint && npm run typecheck
