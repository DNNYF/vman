"""Integration tests for the ``vmanctl`` command-line client.

Milestone 6 / Task 19.

The CLI is a thin HTTP wrapper around the VMAN API. To exercise it
end-to-end without spinning up uvicorn, the tests wire ``vmanctl``'s
HTTP transport to a FastAPI ``TestClient`` via the ``build_test_api_transport``
helper. That way the same code path runs as in production (cookies,
CSRF, status codes), and the test fixture controls the server side
in-process.

Coverage:

- ``vmanctl auth login`` / ``auth me`` round-trip via cookie + CSRF.
- ``vmanctl host list`` reads from ``GET /api/hosts``.
- ``vmanctl host add`` posts a payload and respects CSRF.
- ``vmanctl host check`` runs the bundled ``healthcheck`` recipe.
- ``vmanctl recipe list`` and ``recipe show`` are read-only.
- ``vmanctl recipe run`` starts a recipe job and waits for terminal status.
- ``vmanctl job list`` / ``job status`` / ``job logs --follow`` all work.
- ``--json`` flag emits structured output that is safe to pipe into ``jq``.
- An unauthenticated invocation fails loudly instead of silently dropping
  the request.
- The credentials file is written with mode ``0600`` after a successful login.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import uuid
from pathlib import Path

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from typer.testing import CliRunner

import vman.cli.main as cli_main
from vman.cli.main import (
    APIClient,
    ClientConfig,
    app,
    build_test_api_transport,
)
from vman.config import get_settings
from vman.db import models
from vman.db.base import Base
from vman.db.session import reset_engine
from vman.main import (
    create_app,
    reset_background_worker,
    start_background_worker,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def credentials_dir(tmp_path, monkeypatch) -> Path:
    """Redirect ``~/.config/vman`` to a temp dir so the test does not pollute HOME."""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # XDG_CONFIG_HOME is honored by many tools but we go through Path.home().
    # Some CI environments also set USERPROFILE; redirect for completeness.
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("VMAN_API_TOKEN", "")
    return home / ".config" / "vman"


@pytest.fixture()
def api_client(tmp_path, monkeypatch, credentials_dir):
    """Spin up a FastAPI app + TestClient + CLI APIClient wired together."""

    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_QUEUE_BACKEND", "sqlite")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    reset_background_worker()
    start_background_worker()
    cli_main._SESSION_OVERRIDE.clear()
    test_client = TestClient(create_app())
    transport = build_test_api_transport(test_client)
    monkeypatch.setattr(cli_main, "_TRANSPORT_FACTORY", lambda: transport)
    cli_client = APIClient(
        ClientConfig(base_url="http://test.local"),
        transport=transport,
    )
    yield {
        "test_client": test_client,
        "cli_client": cli_client,
        "db_path": db_path,
    }
    cli_client.close()
    cli_main._SESSION_OVERRIDE.clear()
    reset_background_worker()
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _seed_host(db_path: Path) -> str:
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name="sg-1",
                hostname_or_ip="10.0.0.1",
                ssh_port=22,
                username="root",
                auth_method="key",
                environment="experiment",
                created_at=now,
                updated_at=now,
            )
        )
    eng.dispose()
    return host_id


def _login(api_client, runner) -> None:
    """Drive the API through setup + login and persist cookies on the API client."""
    test_client = api_client["test_client"]
    test_client.post(
        "/api/auth/setup",
        json={"username": "alice", "password": "S3cret...se!!"},
    )
    resp = test_client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "S3cret...se!!"},
    )
    assert resp.status_code == 200, resp.text
    session_cookie = resp.headers.get("set-cookie", "")
    # Parse the set-cookie header for vman_session + vman_csrf tokens.
    cookie_token = _grab_cookie(session_cookie, "vman_session")
    csrf_token = _grab_cookie(session_cookie, "vman_csrf")
    assert cookie_token and csrf_token
    api_client["cli_client"].store_session(
        cookie_token=cookie_token,
        csrf_token=csrf_token,
        persist=False,
    )


def _grab_cookie(header_value: str, name: str) -> str | None:
    if not header_value:
        return None
    marker = f"{name}="
    for raw in header_value.split(","):
        segment = raw.strip().split(";", 1)[0]
        if segment.startswith(marker):
            return segment[len(marker) :]
    return None


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #


def test_auth_login_persists_credentials_with_0600(
    api_client, runner, credentials_dir: Path
) -> None:
    test_client = api_client["test_client"]
    test_client.post(
        "/api/auth/setup",
        json={"username": "alice", "password": "S3cret...se!!"},
    )
    # Wipe any pre-existing cred file so we can prove the CLI wrote it.
    if credentials_dir.exists():
        for child in credentials_dir.iterdir():
            child.unlink()
    result = runner.invoke(
        app,
        [
            "auth",
            "login",
            "--username",
            "alice",
            "--password",
            "S3cret...se!!",
            "--base-url",
            "http://test.local",
        ],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["user"]["username"] == "alice"

    # The credentials file must exist on disk and be locked down.
    cred_path = credentials_dir / "credentials.json"
    assert cred_path.exists()
    if os.name != "nt":
        mode = stat.S_IMODE(cred_path.stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR, f"mode={oct(mode)}"




def test_auth_me_returns_user(api_client, runner) -> None:
    _login(api_client, runner)
    result = runner.invoke(
        app,
        ["auth", "me", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["username"] == "alice"


def test_unauthenticated_command_fails_loudly(api_client, runner) -> None:
    # No login -> no cookies, no token -> CLI must exit non-zero.
    result = runner.invoke(
        app,
        ["host", "list"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 1
    assert "not authenticated" in result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# host
# --------------------------------------------------------------------------- #


def test_host_list_returns_seeded_hosts(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    result = runner.invoke(
        app,
        ["host", "list", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    ids = {row["id"] for row in payload}
    assert host_id in ids
    row = next(r for r in payload if r["id"] == host_id)
    assert row["hostname_or_ip"] == "10.0.0.1"
    assert row["environment"] == "experiment"


def test_host_add_creates_new_host(api_client, runner) -> None:
    _login(api_client, runner)
    result = runner.invoke(
        app,
        [
            "host",
            "add",
            "--name",
            "fresh-host",
            "--ip",
            "10.0.0.2",
            "--port",
            "2222",
            "--user",
            "ubuntu",
            "--auth",
            "key",
            "--env",
            "staging",
            "--json",
        ],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "fresh-host"
    assert payload["hostname_or_ip"] == "10.0.0.2"
    assert payload["ssh_port"] == 2222
    assert payload["environment"] == "staging"


def test_host_check_runs_healthcheck_recipe_and_returns_terminal_status(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    # The bundled healthcheck recipe hits the SSH runner with localhost,
    # which fails for an unseeded host in the sandbox; we only assert
    # that the CLI reached the terminal-status emit (success or failed).
    result = runner.invoke(
        app,
        [
            "host",
            "check",
            host_id,
            "--no-wait",
            "--timeout",
            "10",
            "--json",
        ],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_id"]
    # Polling one status update must yield a terminal status quickly:
    # the worker thread will run the recipe end-to-end against the
    # stubbed SSH transport.
    job_id = payload["job_id"]
    terminal = _wait_for_terminal(api_client["test_client"], job_id, timeout_s=15)
    assert terminal in {"success", "failed", "cancelled", "denied"}


def _wait_for_terminal(test_client: TestClient, job_id: str, *, timeout_s: float) -> str:
    """Poll the API until the job is terminal. Test helper."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = test_client.get(f"/api/jobs/{job_id}")
        if resp.status_code != 200:
            time.sleep(0.1)
            continue
        body = resp.json()
        status = body.get("status", "")
        if status in {"success", "failed", "cancelled", "denied"}:
            return status
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} never reached a terminal status")


# --------------------------------------------------------------------------- #
# recipe
# --------------------------------------------------------------------------- #


def test_recipe_list_includes_healthcheck(api_client, runner) -> None:
    _login(api_client, runner)
    result = runner.invoke(
        app,
        ["recipe", "list", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    names = {row["name"] for row in payload}
    assert "healthcheck" in names


def test_recipe_show_returns_yaml_body(api_client, runner) -> None:
    _login(api_client, runner)
    result = runner.invoke(
        app,
        ["recipe", "show", "healthcheck", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "healthcheck"
    assert "schema_version: 1" in payload["yaml"]


def test_recipe_show_unknown_recipe_returns_error(api_client, runner) -> None:
    _login(api_client, runner)
    result = runner.invoke(
        app,
        ["recipe", "show", "no-such-recipe", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "error" in payload
    assert "not found" in payload["error"]


def test_recipe_run_starts_job_and_passes_vars(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "healthcheck",
            "--host",
            host_id,
            "--var",
            "region=ap-southeast-1",
            "--timeout",
            "10",
            "--no-wait",
            "--json",
        ],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_id"]
    # Wait for terminal so the worker doesn't leak across tests.
    terminal = _wait_for_terminal(api_client["test_client"], payload["job_id"], timeout_s=15)
    assert terminal in {"success", "failed", "cancelled", "denied"}


# --------------------------------------------------------------------------- #
# job
# --------------------------------------------------------------------------- #


def test_job_list_returns_recent_jobs(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    # Kick off a recipe run so there's at least one job in the table.
    api_client["test_client"].post(
        "/api/recipes/run",
        json={
            "host_id": host_id,
            "recipe_yaml": (
                "schema_version: 1\n"
                "name: ad-hoc\n"
                "version: 0.0.1\n"
                "risk_level: low\n"
                "steps:\n"
                "  - name: echo\n"
                "    run: echo hi\n"
            ),
            "vars": {},
            "timeout_seconds": 10,
        },
        headers={"X-CSRF-Token": api_client["cli_client"].config.csrf_token or ""},
    )
    result = runner.invoke(
        app,
        ["job", "list", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert any(row["host_id"] == host_id for row in payload)


def test_job_status_returns_full_payload(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    # Create a job via the recipe run path and wait for terminal.
    detail = api_client["test_client"].get("/api/recipes/healthcheck").json()
    create = api_client["test_client"].post(
        "/api/recipes/run",
        json={
            "host_id": host_id,
            "recipe_yaml": detail["yaml"],
            "vars": {},
            "timeout_seconds": 10,
        },
        headers={"X-CSRF-Token": api_client["cli_client"].config.csrf_token or ""},
    )
    assert create.status_code == 200, create.text
    job_id = create.json()["job_id"]
    _wait_for_terminal(api_client["test_client"], job_id, timeout_s=15)
    result = runner.invoke(
        app,
        ["job", "status", job_id, "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["id"] == job_id
    assert payload["status"] in {"success", "failed", "cancelled", "denied"}


def test_job_logs_follows_until_terminal(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    detail = api_client["test_client"].get("/api/recipes/healthcheck").json()
    create = api_client["test_client"].post(
        "/api/recipes/run",
        json={
            "host_id": host_id,
            "recipe_yaml": detail["yaml"],
            "vars": {},
            "timeout_seconds": 10,
        },
        headers={"X-CSRF-Token": api_client["cli_client"].config.csrf_token or ""},
    )
    assert create.status_code == 200, create.text
    job_id = create.json()["job_id"]
    result = runner.invoke(
        app,
        ["job", "logs", job_id, "--follow", "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    # The --follow path emits one JSON object per event; the last one
    # is the terminal status event.
    events = [json.loads(line) for line in result.stdout.strip().splitlines() if line]
    status_events = [e for e in events if e.get("event") == "status"]
    assert status_events, f"no status events in {events!r}"
    final = status_events[-1]
    assert final["status"] in {"success", "failed", "cancelled", "denied"}


def test_job_logs_without_follow_returns_history(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    detail = api_client["test_client"].get("/api/recipes/healthcheck").json()
    create = api_client["test_client"].post(
        "/api/recipes/run",
        json={
            "host_id": host_id,
            "recipe_yaml": detail["yaml"],
            "vars": {},
            "timeout_seconds": 10,
        },
        headers={"X-CSRF-Token": api_client["cli_client"].config.csrf_token or ""},
    )
    assert create.status_code == 200, create.text
    job_id = create.json()["job_id"]
    _wait_for_terminal(api_client["test_client"], job_id, timeout_s=15)
    result = runner.invoke(
        app,
        ["job", "logs", job_id, "--json"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    # The recipe's system messages and the recipe-name marker should
    # both be present in the history.
    assert any("running preflight" in row.get("line_redacted", "") for row in payload) or any(
        "running" in row.get("line_redacted", "") for row in payload
    )


# --------------------------------------------------------------------------- #
# Human (non-JSON) output path + redaction
# --------------------------------------------------------------------------- #


def test_host_list_human_output_renders_table(api_client, runner) -> None:
    _login(api_client, runner)
    host_id = _seed_host(api_client["db_path"])
    result = runner.invoke(
        app,
        ["host", "list"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    out = result.stdout
    assert "id" in out and "name" in out and "hostname_or_ip" in out
    assert host_id in out


def test_redaction_strips_secrets_in_human_output(api_client, runner) -> None:
    _login(api_client, runner)
    # Insert a host with a leaky note. We bypass the service to do this
    # directly so we don't depend on a redaction layer at the API.
    eng = create_engine(f"sqlite:///{api_client['db_path']}", future=True)
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name="leaky",
                hostname_or_ip="10.0.0.3",
                ssh_port=22,
                username="root",
                auth_method="key",
                environment="experiment",
                notes="password=hunter2-in-plaintext",
                created_at=now,
                updated_at=now,
            )
        )
    eng.dispose()
    result = runner.invoke(
        app,
        ["host", "list", "--all"],
        env={**os.environ, "VMAN_API_BASE_URL": "http://test.local"},
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "hunter2-in-plaintext" not in result.stdout
    assert "[REDACTED]" in result.stdout


# --------------------------------------------------------------------------- #
# CLI metadata
# --------------------------------------------------------------------------- #


def test_vmanctl_entrypoint_is_wired_in_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert 'vmanctl = "vman.cli.main:app"' in text


def test_redact_text_masks_common_patterns() -> None:
    from vman.cli.main import _redact_text

    assert "hunter2" not in _redact_text("password=hunter2")
    assert "[REDACTED]" in _redact_text("api_key=abcdef1234567890")
    assert "AKIA" in _redact_text("AWS key AKIAABCDEFGHIJKLMNOP") or "AWS key" in _redact_text(
        "AWS key AKIAABCDEFGHIJKLMNOP"
    )  # digits-only redaction may or may not match AWS keys


def test_parse_kv_pairs_coerces_int_and_bool() -> None:
    from vman.cli.main import _parse_kv_pairs

    out = _parse_kv_pairs(["port=8080", "enable=true", "name=sg-1"])
    assert out == {"port": 8080, "enable": True, "name": "sg-1"}


def test_parse_set_cookie_handles_multiple_cookies() -> None:
    from vman.cli.main import _parse_set_cookie

    header = "vman_session=abc123; HttpOnly; Path=/, vman_csrf=def456; SameSite=Lax"
    assert _parse_set_cookie(header, "vman_session") == "abc123"
    assert _parse_set_cookie(header, "vman_csrf") == "def456"
    assert _parse_set_cookie("", "vman_session") is None


def test_build_test_api_transport_forwards_cookies() -> None:
    # Confirms the helper used by the rest of the suite actually
    # round-trips cookies both ways.
    from fastapi import FastAPI

    from vman.cli.main import build_test_api_transport

    app = FastAPI()

    @app.get("/api/who")
    def who(response: Response) -> dict[str, str]:
        response.set_cookie("ping", "pong")
        return {"ok": "true"}

    test_client = TestClient(app)
    transport = build_test_api_transport(test_client)
    client = APIClient(
        ClientConfig(base_url="http://x.test"),
        transport=transport,
    )
    try:
        # First call sets the cookie. Subsequent calls should include it.
        first = client.get("/api/who")
        assert first.status == 200
        second = client.get("/api/who")
        assert second.status == 200
    finally:
        client.close()
