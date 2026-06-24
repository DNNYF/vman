# VMAN Deployment Guide

VMAN is optimized for a small central VPS and agentless target VPS nodes. The default production shape is:

- FastAPI backend on `127.0.0.1:8765`.
- Static frontend assets served by the API or reverse proxy.
- SQLite database on local disk.
- Local SQLite-backed worker queue.
- Separate `vman-api` and `vman-worker` systemd services.
- No Redis, Docker, local LLM, or persistent Node.js process required.

## Production configuration checklist

Create `/etc/vman/vman.env` with mode `0600`. `scripts/install-systemd.sh` creates this file from `.env.example` when it is missing, but you must replace the generated placeholders before putting real target credentials into VMAN.

Required values:

```env
VMAN_ENV=production
VMAN_DATABASE_URL=sqlite:////var/lib/vman/vman.db
VMAN_MASTER_KEY=<generate with python scripts/generate-master-key.py>
VMAN_SESSION_SECRET=<generate with python -c "import secrets; print(secrets.token_urlsafe(64))">
VMAN_ALLOWED_ORIGINS=https://vman.example.com
VMAN_API_HOST=127.0.0.1
VMAN_API_PORT=8765
VMAN_FRONTEND_MODE=static
VMAN_QUEUE_BACKEND=sqlite
VMAN_ENABLE_REDIS=false
VMAN_UVICORN_WORKERS=1
VMAN_WORKER_CONCURRENCY=1
VMAN_MAX_PARALLEL_HOST_JOBS=1
VMAN_MAX_GLOBAL_JOBS=1
VMAN_LOG_RETENTION_DAYS=7
VMAN_METRICS_RETENTION_DAYS=7
```

Optional reverse proxy setting:

```env
# Use only when Cloudflare Tunnel/Caddy/Nginx is trusted to set X-Forwarded-For.
VMAN_TRUSTED_PROXY_HOPS=1
```

Leave `VMAN_TRUSTED_PROXY_HOPS=0` when VMAN is directly exposed or when the proxy does not sanitize client-supplied forwarding headers.

## Install or upgrade with systemd

Run from the central VPS:

```bash
git clone https://github.com/alamakmak/vman.git /home/ubuntu/vman
cd /home/ubuntu/vman
uv venv --python 3.12 .venv
uv pip install -e '.[dev]'
python scripts/generate-master-key.py
sudo bash scripts/install-systemd.sh
sudo editor /etc/vman/vman.env
sudo systemctl restart vman-api vman-worker
curl -fsS http://127.0.0.1:8765/api/health
```

The installer is idempotent. It writes:

- `/etc/vman/vman.env` if missing, with root-only permissions and deployment placeholders.
- `/etc/systemd/system/vman-api.service` for the API process.
- `/etc/systemd/system/vman-worker.service` for the background worker process.

It then runs `systemctl daemon-reload`, enables both services, restarts them by default, and prints the health check command. For a dry run or packaging test, set `VMAN_SKIP_SYSTEMCTL=1` and override `VMAN_SYSTEMD_DIR`, `VMAN_CONFIG_DIR`, and `VMAN_VARLIB_DIR`.

Useful overrides:

```bash
sudo VMAN_REPO_ROOT=/opt/vman \
  VMAN_ENV_FILE=/etc/vman/vman.env \
  VMAN_START_SERVICES=0 \
  bash scripts/install-systemd.sh
```

## Health endpoint and smoke test

After every install, upgrade, or environment change:

```bash
sudo systemctl status vman-api --no-pager
sudo systemctl status vman-worker --no-pager
curl -fsS http://127.0.0.1:8765/api/health
python -m pytest tests/integration/test_auth_api.py tests/integration/test_csrf.py -q
```

A healthy API response looks like:

```json
{"status":"ok","service":"vman","version":"0.1.0"}
```

If the health check fails, inspect logs:

```bash
sudo journalctl -u vman-api -n 100 --no-pager
sudo journalctl -u vman-worker -n 100 --no-pager
```

Do not add real target credentials until health, auth, CSRF/CORS, policy, audit, and backup checks pass.

## Cloudflare Tunnel recommendation

For VPS providers that expose only a non-standard inbound SSH port, run the dashboard behind an outbound Cloudflare Tunnel instead of opening 80/443. Point the public hostname at `http://127.0.0.1:8765` and set `VMAN_ALLOWED_ORIGINS` to that HTTPS hostname.

## Backup and restore reminder

The SQLite database contains encrypted credential payloads, audit events, jobs, and host inventory. A DB backup is useful only with the correct `VMAN_MASTER_KEY`. Store the master key separately from routine DB backups unless you intentionally need a full disaster-recovery bundle.
