"""Integration tests for the recipe HTTP routes (Task 18).

Covers:
- ``GET /api/recipes`` returns at least the bundled healthcheck.
- ``GET /api/recipes/{name}`` returns the YAML body for a known name
  and 404s for an unknown one.
- ``POST /api/recipes/run`` creates a recipe job, returns the job id
  and stores ``recipe_name`` on the job row so the jobs dashboard can
  link the run back to the catalogue.
- ``POST /api/recipes/validate`` rejects malformed recipes with 422.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from vman.config import get_settings
from vman.db import models
from vman.db.base import Base
from vman.db.session import get_sessionmaker, reset_engine
from vman.main import create_app, reset_background_worker, start_background_worker


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("VMAN_QUEUE_BACKEND", "sqlite")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    reset_background_worker()
    start_background_worker()
    yield TestClient(create_app())
    reset_background_worker()
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _setup_and_login(client: TestClient) -> str:
    client.post(
        "/api/auth/setup",
        json={"username": "alice", "password": "S3cret-passphrase!!"},
    )
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "S3cret-passphrase!!"},
    )
    return client.cookies.get("vman_csrf") or ""


def _csrf(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def _seed_host(db_path) -> str:
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name="host-x",
                hostname_or_ip="127.0.0.1",
                ssh_port=22,
                username="root",
                auth_method="key",
                created_at=now,
                updated_at=now,
            )
        )
    eng.dispose()
    return host_id


def test_list_recipes_returns_healthcheck(client: TestClient) -> None:
    _setup_and_login(client)
    resp = client.get("/api/recipes")
    assert resp.status_code == 200
    rows = resp.json()
    names = {r["name"] for r in rows}
    assert "healthcheck" in names
    row = next(r for r in rows if r["name"] == "healthcheck")
    assert row["risk_level"] == "low"
    assert row["step_count"] >= 1
    assert row["has_preflight"] is True
    assert row["has_verify"] is True
    assert row["vars"] == {}


def test_get_recipe_returns_yaml_body(client: TestClient) -> None:
    _setup_and_login(client)
    resp = client.get("/api/recipes/healthcheck")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "healthcheck"
    assert "schema_version: 1" in body["yaml"]
    assert "name: healthcheck" in body["yaml"]


def test_get_unknown_recipe_404s(client: TestClient) -> None:
    _setup_and_login(client)
    resp = client.get("/api/recipes/does-not-exist")
    assert resp.status_code == 404


def test_validate_rejects_malformed_yaml(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.post(
        "/api/recipes/validate",
        json={"recipe_yaml": "this is :: not yaml :: : :"},
        headers=_csrf(csrf),
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert isinstance(detail, str) and detail


def test_run_recipe_creates_job_and_persists_recipe_name(client: TestClient, tmp_path) -> None:
    csrf = _setup_and_login(client)
    host_id = _seed_host(tmp_path / "vman.db")
    # Load the bundled healthcheck recipe to drive the run path.
    detail = client.get("/api/recipes/healthcheck").json()
    resp = client.post(
        "/api/recipes/run",
        json={
            "host_id": host_id,
            "recipe_yaml": detail["yaml"],
            "vars": {},
            "timeout_seconds": 30,
        },
        headers=_csrf(csrf),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] in {"queued", "running", "success", "failed"}
    assert payload["job_id"]

    # The recipe name must be persisted on the job row so the
    # dashboard can link the run back to the recipe catalogue.
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        job = s.get(models.Job, payload["job_id"])
        assert job is not None
        assert job.recipe_name == "healthcheck"
