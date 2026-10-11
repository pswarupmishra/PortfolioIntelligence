# Server Deployment Guide

This guide deploys Jira Executive Portfolio Intelligence on a Linux server with FastAPI managed by `systemd`, the React production build served by Nginx, and SQLite stored on persistent local disk. The recommended layout uses one public HTTPS origin, so browser requests to `/api` are reverse-proxied to FastAPI and CORS is avoided in normal operation.

## 1. Choose the public URL and architecture

The recommended URL is:

```text
https://portfolio.example.com
```

Nginx serves React and forwards `https://portfolio.example.com/api/...` to FastAPI at `http://127.0.0.1:8000/api/...`. FastAPI and SQLite are not exposed directly to the internet.

Important production constraints:

- Use one Uvicorn worker. SQLite and the application's process-local synchronization lock are designed for one backend process.
- Store the SQLite file on persistent local disk, not ephemeral container storage or shared network storage.
- Keep `.env` readable only by the service account.
- Use HTTPS before exposing login sessions outside a trusted network.
- Back up the SQLite database and its WAL files consistently.

## 2. Prepare an Ubuntu server

Run these commands as a user with `sudo` access:

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip curl
```

Install Node.js 20 or newer using your organization's approved package source, then verify:

```bash
python3 --version
node --version
npm --version
nginx -v
```

Create a dedicated service account and application directory:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin portfolioapp
sudo mkdir -p /opt/portfolio-intelligence /var/lib/portfolio-intelligence
sudo chown -R portfolioapp:portfolioapp /opt/portfolio-intelligence /var/lib/portfolio-intelligence
```

## 3. Clone and install the application

```bash
sudo -u portfolioapp git clone https://github.com/pswarupmishra/PortfolioIntelligence.git /opt/portfolio-intelligence/source
cd /opt/portfolio-intelligence/source/jira_portfolio_App
sudo -u portfolioapp python3 -m venv .venv
sudo -u portfolioapp .venv/bin/python -m pip install --upgrade pip
sudo -u portfolioapp .venv/bin/python -m pip install -e './backend[dev]'
sudo -u portfolioapp npm --prefix frontend ci
```

For a locked-down production build, the `dev` dependency group may be omitted after your deployment pipeline has run its tests. It is included above so migrations and validation commands match the repository workflow.

## 4. Create the server environment file

Create `/opt/portfolio-intelligence/source/jira_portfolio_App/.env`:

```dotenv
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-service-account@example.com
JIRA_API_TOKEN=replace-with-a-new-server-side-token
DATABASE_URL=sqlite:////var/lib/portfolio-intelligence/jira_portfolio.db
CORS_ORIGINS=["https://portfolio.example.com"]
JIRA_MAX_RETRIES=3
JIRA_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
```

Then protect it:

```bash
sudo chown portfolioapp:portfolioapp /opt/portfolio-intelligence/source/jira_portfolio_App/.env
sudo chmod 600 /opt/portfolio-intelligence/source/jira_portfolio_App/.env
```

Notes:

- Use the Jira site root only; do not include `/jira`, `/browse`, or an issue path.
- The absolute SQLite URL has four slashes after `sqlite:`.
- Never put the Jira token in React variables, Nginx files, Git, or browser-side code.
- `CORS_ORIGINS` is a JSON array. Each entry must be an exact browser origin: scheme, hostname, and optional port, with no path or trailing slash.

## 5. Run database migrations

```bash
cd /opt/portfolio-intelligence/source/jira_portfolio_App/backend
sudo -u portfolioapp ../.venv/bin/alembic upgrade head
```

Verify the database directory and file permissions:

```bash
sudo -u portfolioapp test -w /var/lib/portfolio-intelligence
sudo -u portfolioapp ls -l /var/lib/portfolio-intelligence
```

The database file is created by the migration. The application enables SQLite foreign keys and WAL mode automatically.

## 6. Build React for same-origin API access

Build with an empty API base URL so the browser requests `/api/v1/...` from the same public origin as the page:

```bash
cd /opt/portfolio-intelligence/source/jira_portfolio_App/frontend
sudo -u portfolioapp env VITE_API_URL= npm run build
```

The production files are generated in `frontend/dist`. `VITE_API_URL` is compiled into the JavaScript bundle; changing it later requires rebuilding the frontend.

Confirm that no Jira secret was bundled:

```bash
grep -R "JIRA_API_TOKEN\|ATATT" /opt/portfolio-intelligence/source/jira_portfolio_App/frontend/dist || true
```

This command should produce no matches.

## 7. Run FastAPI with systemd

Create `/etc/systemd/system/portfolio-intelligence.service`:

```ini
[Unit]
Description=Jira Portfolio Intelligence API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=portfolioapp
Group=portfolioapp
WorkingDirectory=/opt/portfolio-intelligence/source/jira_portfolio_App/backend
ExecStart=/opt/portfolio-intelligence/source/jira_portfolio_App/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

The backend loads `../.env` from this working directory through its settings module. It is intentionally not declared as a systemd `EnvironmentFile`, because systemd's quote processing can alter the JSON syntax used by `CORS_ORIGINS`.

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-intelligence
sudo systemctl status portfolio-intelligence --no-pager
curl http://127.0.0.1:8000/api/v1/health/live
curl http://127.0.0.1:8000/api/v1/health/ready
```

Expected liveness response:

```json
{"status":"ok"}
```

View backend logs with:

```bash
sudo journalctl -u portfolio-intelligence -f
```

## 8. Configure Nginx

Create `/etc/nginx/sites-available/portfolio-intelligence`:

```nginx
server {
    listen 80;
    server_name portfolio.example.com;

    root /opt/portfolio-intelligence/source/jira_portfolio_App/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
        try_files $uri =404;
    }
}
```

The `try_files ... /index.html` fallback is required for React routes such as `/cards` and `/maintenance` to work after a browser refresh.

Enable the site and test it:

```bash
sudo ln -s /etc/nginx/sites-available/portfolio-intelligence /etc/nginx/sites-enabled/portfolio-intelligence
sudo nginx -t
sudo systemctl reload nginx
curl -I http://portfolio.example.com
curl http://portfolio.example.com/api/v1/health/live
```

If Nginx cannot read `frontend/dist`, grant the `www-data` user directory traversal/read access using your organization's preferred ownership or ACL policy. Do not make `.env` world-readable.

## 9. Enable HTTPS

Use the TLS certificate process approved by your organization. With Certbot on a public server:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d portfolio.example.com
```

After HTTPS is enabled, confirm `.env` contains the HTTPS origin:

```dotenv
CORS_ORIGINS=["https://portfolio.example.com"]
```

Restart FastAPI after changing `.env`:

```bash
sudo systemctl restart portfolio-intelligence
```

## 10. First sign-in and Jira initialization

1. Open `https://portfolio.example.com`.
2. Sign in with the initial local administrator account.
3. Immediately change the default password under **App Setting → Maintenance → User management**.
4. Open **App Setting → Maintenance → Jira connection**.
5. Test the connection and refresh metadata.
6. Activate the required Jira projects and fields.
7. Run a full synchronization under **App Setting → Portfolio Sync → Sync Monitoring**.
8. Configure Traceability/Sprint levels and their independent grids.

## 11. Understanding and fixing CORS

### Recommended same-origin deployment

When React uses `VITE_API_URL=` and Nginx proxies `/api`, the browser sees only `https://portfolio.example.com`. Requests are same-origin and do not require a cross-origin CORS exchange. Keep the public hostname in `CORS_ORIGINS` as a safe allowance for direct API tooling and future topology changes.

### Separate frontend and API origins

If React is served from `https://portfolio.example.com` but calls `https://portfolio-api.example.com`, rebuild with:

```bash
cd /opt/portfolio-intelligence/source/jira_portfolio_App/frontend
sudo -u portfolioapp env VITE_API_URL=https://portfolio-api.example.com npm run build
```

Set the backend environment to the frontend origin, not the API origin:

```dotenv
CORS_ORIGINS=["https://portfolio.example.com"]
```

Then restart the API and reload Nginx:

```bash
sudo systemctl restart portfolio-intelligence
sudo systemctl reload nginx
```

For more than one allowed UI origin:

```dotenv
CORS_ORIGINS=["https://portfolio.example.com","https://portfolio-dr.example.com"]
```

Do not use `*`: the application sends an `Authorization` header and enables credential-aware CORS handling, which requires explicit trusted origins.

### Test the preflight response

Run this against the API origin:

```bash
curl -i -X OPTIONS https://portfolio-api.example.com/api/v1/auth/login \
  -H 'Origin: https://portfolio.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,authorization'
```

The response should include:

```text
access-control-allow-origin: https://portfolio.example.com
access-control-allow-methods: GET, POST, PUT, DELETE
```

### CORS troubleshooting checklist

1. In browser developer tools, inspect the failed request's **Request URL** and **Origin**.
2. Confirm the exact Origin is present in `CORS_ORIGINS`; `http` and `https`, hostnames, and ports are different origins.
3. Remove paths and trailing slashes from `CORS_ORIGINS` entries.
4. If `VITE_API_URL` changed, rebuild React and deploy the new `frontend/dist`; restarting Nginx alone is insufficient.
5. Restart FastAPI after changing `.env`; environment settings are loaded when the process starts.
6. Confirm Nginx allows `OPTIONS` through to FastAPI and does not overwrite CORS headers.
7. Check `journalctl -u portfolio-intelligence` and the browser Network panel. A `401`, `403`, `404`, or `502` is not necessarily a CORS failure even if the browser message is vague.
8. Avoid adding CORS headers in both Nginx and FastAPI. Let FastAPI produce them to prevent duplicate or contradictory headers.

Common symptoms:

| Symptom | Likely cause | Correction |
|---|---|---|
| No `Access-Control-Allow-Origin` | Frontend origin is absent or malformed | Add the exact frontend origin and restart FastAPI |
| Preflight returns `404`/`405` | Proxy did not forward `OPTIONS` to FastAPI | Check the Nginx `/api/` location and `proxy_pass` |
| Browser calls `localhost:8000` | Production bundle used the development default | Rebuild with empty or correct production `VITE_API_URL` |
| API returns `502 Bad Gateway` | Uvicorn is stopped or Nginx points to the wrong port | Check `systemctl status` and `127.0.0.1:8000` |
| Login works in curl but not browser | Origin mismatch, stale frontend bundle, or proxy issue | Inspect preflight, rebuild React, and verify exact origins |
| React route gives Nginx `404` | SPA fallback is missing | Add `try_files $uri $uri/ /index.html` |

## 12. Updates and rollback preparation

Before an update, back up SQLite while the service is stopped:

```bash
sudo systemctl stop portfolio-intelligence
sudo -u portfolioapp cp /var/lib/portfolio-intelligence/jira_portfolio.db /var/lib/portfolio-intelligence/jira_portfolio.db.backup
sudo systemctl start portfolio-intelligence
```

Deploy an update:

```bash
cd /opt/portfolio-intelligence/source
sudo -u portfolioapp git pull --ff-only
cd jira_portfolio_App
sudo -u portfolioapp .venv/bin/python -m pip install -e './backend[dev]'
sudo -u portfolioapp npm --prefix frontend ci
cd backend
sudo -u portfolioapp ../.venv/bin/alembic upgrade head
cd ../frontend
sudo -u portfolioapp env VITE_API_URL= npm run build
sudo systemctl restart portfolio-intelligence
sudo nginx -t
sudo systemctl reload nginx
```

Run smoke checks after every deployment:

```bash
curl https://portfolio.example.com/api/v1/health/live
curl https://portfolio.example.com/api/v1/health/ready
```

Then sign in, open Overview, test Jira Connection, and verify one read-only project view.

## 13. Backup and operational notes

- Schedule regular SQLite backups and test restoration. Stop the service or use SQLite's online backup mechanism so the database and WAL state are consistent.
- Monitor disk space in `/var/lib/portfolio-intelligence` and system logs for sync failures.
- Do not run multiple Uvicorn workers or multiple backend instances against this SQLite file.
- Restrict `/docs` at the reverse proxy if API documentation should not be public.
- Rotate the Jira API token and local administrator password according to organizational policy.
- For multi-instance deployment or heavier concurrent writes, migrate from SQLite to PostgreSQL and move synchronization to a dedicated worker before scaling horizontally.
