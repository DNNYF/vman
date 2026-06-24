# VMAN Architecture

This is the human-readable companion to the implementation plan at
`.hermes/plans/2026-06-22_140720-vman-secure-vps-manager.md`. The plan is the
source of truth for scope and ordering; this document explains how the pieces
fit together once they exist.

## High-level model

VMAN is a **control plane that runs on one central VPS** and manages many
small target VPSes over SSH. The central VPS owns all the intelligence:

- inventory
- credentials
- recipes
- jobs and audit log
- the worker that actually opens SSH sessions

Targets stay boring: SSH server, shell, coreutils, a package manager. **No
agent, no Python, no Node, no DB on the target.**

```
                        +-----------------------+
                        |     Central VPS       |
   Dashboard (browser)  |                       |
   <------------------> |  FastAPI  +  Worker   |
                        |  SQLite  +  Vault     |
                        |  Recipe Engine        |
                        +----------+------------+
                                   |
                          SSH      |    (strict host key check,
                          only     |     encrypted creds in memory)
                                   v
                        +-----------------------+
                        |   Target VPS          |
                        |   OpenSSH + shell     |
                        +-----------------------+
```

## Components (current and planned)

| Layer | Component | Status | Milestone |
|---|---|---|---|
| API | FastAPI app with `/api/health` | **shipped** | M0 |
| Config | Strict settings + production safety net | **shipped** | M0 |
| DB | SQLAlchemy 2 models + Alembic | next | M0 / T2 |
| Crypto | AES-256-GCM credential vault | next | M0 / T3 |
| Redaction | Secret-pattern scrubbing | next | M0 / T4 |
| Auth | Argon2id sessions, login/logout | next | M1 |
| Audit | Append-only audit log | next | M1 |
| Hosts | CRUD + fingerprint trust | next | M2 |
| SSH runner | AsyncSSH runner with strict host keys | next | M2 |
| Job queue | SQLite/local queue + worker | next | M3 |
| Policy | Risk classification + approval | next | M3 |
| Recipes | YAML schema + engine | next | M4 |
| Dashboard | Vite React SPA (static build) | next | M5 |
| CLI | `vmanctl` (Typer) | next | M6 |
| MCP | `vman-mcp` constrained tools | next | M8 |
| Built-in recipes | healthcheck, install-9router, etc. | next | M9 |
| Deployment | systemd units, Cloudflare Tunnel docs | next | M10 |

## Process and security boundaries

- **API process** serves HTTP, holds no decrypted credentials longer than a
  single request. Sessions are cookie-based and signed with `VMAN_SESSION_SECRET`.
- **Worker process** is the only thing allowed to decrypt credentials. It runs
  as a separate systemd unit so it can be paused independently in an emergency.
- **Database** lives on the central VPS only. SQLite for MVP; PostgreSQL-ready
  abstraction later.
- **Vault keys** never touch the database. `VMAN_MASTER_KEY` is loaded from
  the environment (env file, not committed).

## Threat model summary

The full threat model is in section 2 of the implementation plan. The
non-negotiables for every component:

1. No plaintext credentials in the DB, logs, API responses, or the dashboard.
2. No `print()` of secrets anywhere -- the redaction engine (M0/T4) catches
   the obvious patterns in logs and tool outputs.
3. Every sensitive action creates an audit event.
4. Destructive actions are gated by the policy engine (M3/T12).
5. Host key fingerprints must be verified before any SSH command runs.
6. Production deploys MUST refuse to boot with placeholder secrets (see
   `Settings.model_post_init`).

## Low-resource design constraints

The central VPS this runs on may be a 1 vCPU / 2 GB RAM machine that already
runs Hermes/Alice and other sidecars. The following defaults are mandatory
and documented in `.env.example`:

- `VMAN_DATABASE_URL` = SQLite (no PostgreSQL service required)
- `VMAN_QUEUE_BACKEND` = `sqlite` (no Redis required)
- `VMAN_UVICORN_WORKERS` = 1
- `VMAN_WORKER_CONCURRENCY` = 1
- `VMAN_MAX_PARALLEL_HOST_JOBS` = 1
- `VMAN_MAX_GLOBAL_JOBS` = 1
- `VMAN_FRONTEND_MODE` = `static` (no Node process in production)
- `VMAN_ENABLE_REDIS` = `false`
- `VMAN_ENABLE_PLAYWRIGHT_LOCAL` = `false`

Heavy validation that the small VPS cannot run reliably (full Playwright
matrix, full frontend production build, security scans across the whole
tree) happens in GitHub Actions instead.

## Where to look next

- `docs/operations.md` -- day-to-day running
- `docs/security.md` -- secrets, rotation, audit, policy
- `docs/recipes.md` -- recipe DSL and the recipe library
- `docs/deployment.md` -- systemd, Cloudflare Tunnel, backups
- `docs/mcp-integration.md` -- exposing VMAN to Alice/Hermes
- `docs/vibe-coding-runbook.md` -- how to keep iterating from the small VPS
