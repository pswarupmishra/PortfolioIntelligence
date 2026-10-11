# Local Setup Guide

This guide installs and runs Jira Executive Portfolio Intelligence locally with React, FastAPI, and SQLite. Jira credentials stay in a local `.env` file and must never be committed.

## 1. Install the prerequisites

Install:

- Git
- Python 3.10 or newer; Python 3.12 is recommended
- Node.js 20 or newer
- npm, which is included with Node.js
- A Jira Cloud account with permission to read the projects and issues you want to synchronize
- A Jira Cloud API token for that account

Verify the tools:

```bash
git --version
python3 --version
node --version
npm --version
```

## 2. Clone the repository

```bash
git clone https://github.com/pswarupmishra/PortfolioIntelligence.git
cd PortfolioIntelligence/jira_portfolio_App
```

All remaining commands in this guide assume that the current directory is `jira_portfolio_App`.

## 3. Create the Python virtual environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

After activation, the terminal prompt normally includes `(.venv)`.

## 4. Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e './backend[dev]'
```

This installs FastAPI, Uvicorn, SQLAlchemy, Alembic, the Jira HTTP client, and the backend test tools.

## 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

## 6. Create the backend `.env` file

Copy the safe template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor and replace the placeholder values:

```dotenv
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-jira-account@example.com
JIRA_API_TOKEN=your-jira-api-token
DATABASE_URL=sqlite:///./jira_portfolio.db
CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
JIRA_MAX_RETRIES=3
JIRA_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
```

Important rules:

1. `JIRA_BASE_URL` must contain the Jira site URL without `/jira`, `/browse`, or a trailing issue path.
2. `JIRA_EMAIL` must be the account associated with the API token.
3. `JIRA_API_TOKEN` must contain an Atlassian API token, not the Jira account password.
4. Do not add quotes around ordinary values unless the quotes are part of the value.
5. Never commit or share `.env`. It is already excluded by `.gitignore`.
6. If a token has been pasted into chat, email, source code, or a committed file, revoke it and generate a new token.

The frontend never receives these Jira credentials. FastAPI reads them on the server and makes read-only Jira calls.

## 7. Configure SQLite

The default setting is:

```dotenv
DATABASE_URL=sqlite:///./jira_portfolio.db
```

Because backend commands run from the `backend` directory, this creates:

```text
jira_portfolio_App/backend/jira_portfolio.db
```

SQLite does not require a separate database server, username, or password. The application enables foreign keys and WAL mode automatically.

Create or upgrade the database schema:

```bash
make migrate
```

Equivalent manual command:

```bash
cd backend
alembic upgrade head
cd ..
```

Confirm the applied migration version:

```bash
cd backend
alembic current
cd ..
```

The current database should report the latest migration revision.

### Back up the local SQLite database

Stop the backend before copying the database. Then run:

```bash
cp backend/jira_portfolio.db backend/jira_portfolio.backup.db
```

The database, WAL files, and backup `.db` files are excluded from Git.

### Start with a new SQLite database

Stop the application and move the existing database to a recoverable backup:

```bash
mv backend/jira_portfolio.db backend/jira_portfolio.previous.db
make migrate
```

Do not move the database while FastAPI is running. If `jira_portfolio.db-wal` or `jira_portfolio.db-shm` exists, shut down the backend cleanly before backing up or replacing the database.

## 8. Start the application

The simplest option starts both services and runs migrations first:

```bash
make dev
```

Open:

- Application: `http://127.0.0.1:5173`
- FastAPI documentation: `http://127.0.0.1:8000/docs`
- Backend readiness check: `http://127.0.0.1:8000/api/v1/health/ready`

Stop both services with `Ctrl+C` in the terminal running `make dev`.

### Run the services in separate terminals

Terminal 1:

```bash
cd jira_portfolio_App
source .venv/bin/activate
make backend
```

Terminal 2:

```bash
cd jira_portfolio_App
source .venv/bin/activate
make frontend
```

For Windows, activate the virtual environment with `.\.venv\Scripts\Activate.ps1`, then run the equivalent commands inside `backend` and `frontend` if `make` is unavailable.

Backend:

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second PowerShell window:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

## 9. Complete the first-time application setup

In the application:

1. Open **App Setting → Configuration → Jira connection**.
2. Select **Test connection**. Confirm that the connected Jira display name appears.
3. Select **Refresh metadata**. This discovers projects, issue types, statuses, standard fields, custom fields, contexts, and options.
4. Enable the project or projects to include in the portfolio.
5. Open **App Setting → Portfolio Sync → Sync Monitoring**.
6. Run **Full sync** for the initial data load.
7. Wait for the sync to finish and confirm the fetched issue count.
8. Configure **Traceability configuration**, **Sprint View configuration**, and **Grid configuration** as required.
9. Open Portfolio View or Execution View and select the project.

Use **Incremental sync** after the initial full sync. Periodically run a full sync so issues deleted from Jira or no longer accessible can be reconciled locally.

## 10. Configure a non-default frontend API address

The frontend defaults to `http://localhost:8000`. If the backend uses another host or port, create `frontend/.env.local`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Restart the frontend after changing `VITE_API_URL`. Do not place Jira credentials in any `VITE_` variable because Vite exposes those values to the browser.

## 11. Run validation checks

With the virtual environment activated:

```bash
make test
make lint
cd frontend
npm run build
cd ..
```

Backend tests use mocked Jira responses and do not require live Jira credentials.

## 12. Update an existing local installation

Stop the running application, then run:

```bash
git pull origin main
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cd frontend
npm install
cd ..
make migrate
make dev
```

Running `make migrate` after every pull safely applies newly added schema migrations without deleting existing synchronized data.

## Troubleshooting

### `Jira credentials are not configured`

- Confirm that `.env` is located in `jira_portfolio_App/.env`.
- Confirm all three variables are present: `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN`.
- Restart FastAPI after changing `.env`.

### Jira returns 401

- Confirm the email address belongs to the token owner.
- Generate a new Atlassian API token and update `JIRA_API_TOKEN`.
- Ensure the token contains no copied spaces or line breaks.

### Jira returns 403 or some fields are missing

- The Jira account lacks permission for that project, issue, field context, or field option endpoint.
- Ask a Jira administrator to grant the minimum required read permissions.
- Refresh metadata after permissions change.

### `database is locked`

- Ensure only one sync writer is running.
- Stop duplicate backend processes.
- Do not copy, move, or replace the SQLite file while FastAPI is running.

### The frontend cannot reach the backend

- Confirm `http://127.0.0.1:8000/api/v1/health/ready` responds.
- Confirm ports `5173` and `8000` are available.
- Check `CORS_ORIGINS` in `.env`.
- If using a different backend address, configure `frontend/.env.local` and restart Vite.

### Optional grid or grouping fields have no values

- Run a full Jira sync after selecting or discovering new fields.
- Confirm the field is populated on issues in the selected Jira project.
- Confirm the Jira account can view that field.

## Local security checklist

- Keep `.env` only on the local machine.
- Never commit Jira API tokens, SQLite databases, `.db-wal`, or `.db-shm` files.
- Use a dedicated Jira service account with read-only access where possible.
- Revoke exposed tokens immediately.
- Do not expose the development server directly to the internet.
- Replace the development `X-App-Role` boundary with trusted SSO or proxy authentication before production deployment.
