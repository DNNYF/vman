# VMAN v0.1.0 Release Checklist

Use this checklist for every release tag.

## 1. Source and version

- `pyproject.toml` `[project].version` matches `backend/vman/__init__.py` `__version__`.
- `README.md` status reflects the released MVP state.
- `uv.lock` is refreshed with the current dependency set.
- No `.env`, private keys, database files, or generated backups are tracked.

## 2. Security hardening review

- CORS is restricted to explicit configured origins.
- Production rejects HTTP or wildcard CORS origins.
- CSRF is enforced for authenticated mutating browser requests.
- Login is rate-limited by source IP and username-derived key.
- Session cookies are HttpOnly; session and CSRF cookies are Secure in production.
- `X-Forwarded-For` is ignored unless `VMAN_TRUSTED_PROXY_HOPS > 0`.
- Audit events are redacted and hash-chained.
- Built-in recipes that change firewall, SSH, users, services, or packages declare appropriate risk/approval policy.

## 3. Local verification

Run from the repository root:

```bash
python -m pytest -q
ruff check backend tests scripts
python -m mypy backend/vman
```

Optional smoke checks:

```bash
python -m pytest tests/integration/test_auth_api.py tests/integration/test_csrf.py -q
python -m pytest tests/integration/test_builtin_recipe_pack.py -q
```

## 4. Deployment smoke

- Install or upgrade on a staging control VPS.
- Start `vman-api` and `vman-worker` with systemd.
- Confirm `curl -fsS http://127.0.0.1:8765/api/health` returns status `ok`.
- Create a first admin in a temporary staging database.
- Login, logout, and verify CSRF-protected requests behave correctly.
- Run a read-only healthcheck recipe against a disposable target or mocked runner.

## 5. Tag and push

```bash
git status --short
git tag -a v0.1.0 -m "v0.1.0"
git push origin main
git push origin v0.1.0
```

If the remote moved, run:

```bash
git pull --rebase --autostash origin main
git push origin main
git push origin v0.1.0
```

## 6. Post-release

- Confirm GitHub CI and security workflows complete successfully for the release commit/tag.
- Record any dependency audit exceptions in the next maintenance issue before real credentials are added.
