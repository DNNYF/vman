# VMAN — Secure Agentless VPS Fleet Manager

VMAN is a high-security, agentless control plane for managing many small VPS targets from one central VPS. Targets only need SSH; everything else lives on the control plane.

Key properties:

- Agentless targets (no Hermes, no Python venv, no Node, no DB on the target)
- Encrypted credential vault (AES-256-GCM envelope encryption)
- Strict host-key verification, audited job system, recipe engine
- Static Vite React frontend served by the API (no Node process required in production)
- SQLite + local queue by default; no Docker, no Redis, no local LLM required
- Built for small central VPS (1 vCPU / ~2 GB RAM / ~2 GB swap)
- `vmanctl` CLI and constrained MCP server integration

See `docs/architecture.md` for the full design and `.hermes/plans/2026-06-22_140720-vman-secure-vps-manager.md` for the implementation plan.

## Status

v0.1.0 MVP release candidate. The backend, dashboard shell, CLI, MCP server, built-in recipes, security CI, deployment docs, backup/export path, and final hardening checks are in place. Review `docs/security.md`, `docs/deployment.md`, and `docs/release-checklist.md` before adding real credentials.

## Quick start (development)

```bash
# Python 3.12+ recommended; 3.10+ also works
uv venv --python 3.12 .venv  # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
ruff check backend tests scripts
python -m mypy backend/vman
uvicorn vman.main:app --reload --port 8765
curl http://127.0.0.1:8765/api/health
```

## Release docs

- `docs/security.md` — browser/API hardening, audit chain, credential safety, release gate.
- `docs/deployment.md` — production environment checklist and systemd smoke test.
- `docs/release-checklist.md` — v0.1.0 release/tag checklist.

## License

TBD — to be decided by the maintainer before the first release.
