"""Integration tests for the application settings API (Phase 2)."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from vman.config import get_settings
from vman.db.session import reset_engine
from vman.main import create_app


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    dotenv_path = tmp_path / ".env"
    
    # Write initial .env file contents
    initial_dotenv = (
        "VMAN_ENV=development\n"
        "VMAN_API_HOST=127.0.0.1\n"
        "VMAN_API_PORT=8000\n"
        "VMAN_DATABASE_URL=sqlite:///./data/vman.db\n"
        "VMAN_LOG_LEVEL=INFO\n"
        "VMAN_LOG_RETENTION_DAYS=7\n"
        "VMAN_METRICS_RETENTION_DAYS=7\n"
        "VMAN_UVICORN_WORKERS=1\n"
        "VMAN_WORKER_CONCURRENCY=1\n"
        "VMAN_SSH_CONNECT_TIMEOUT_SECONDS=10\n"
        "VMAN_SSH_COMMAND_TIMEOUT_SECONDS=300\n"
    )
    dotenv_path.write_text(initial_dotenv, encoding="utf-8")
    
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", str(dotenv_path))
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    
    from sqlalchemy import create_engine
    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    
    yield TestClient(create_app()), dotenv_path
    
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


def test_get_settings_succeeds(settings_client) -> None:
    client, _ = settings_client
    csrf = _setup_and_login(client)

    resp = client.get("/api/settings", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["env"] == "development"
    assert body["api_host"] == "127.0.0.1"
    assert body["api_port"] == 8000
    assert body["log_level"] == "INFO"
    assert "master_key" not in body
    assert "session_secret" not in body


def test_update_settings_succeeds(settings_client) -> None:
    client, dotenv_path = settings_client
    csrf = _setup_and_login(client)

    updates = {
        "log_level": "DEBUG",
        "api_port": 9000,
        "ssh_connect_timeout_seconds": 15,
    }
    resp = client.post("/api/settings", json=updates, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["log_level"] == "DEBUG"
    assert body["api_port"] == 9000
    assert body["ssh_connect_timeout_seconds"] == 15

    # Check that .env file was modified
    dotenv_content = dotenv_path.read_text(encoding="utf-8")
    assert "VMAN_LOG_LEVEL=DEBUG" in dotenv_content
    assert "VMAN_API_PORT=9000" in dotenv_content
    assert "VMAN_SSH_CONNECT_TIMEOUT_SECONDS=15" in dotenv_content


def test_update_settings_invalid_values_fails(settings_client) -> None:
    client, _ = settings_client
    csrf = _setup_and_login(client)

    # uvicorn_workers must be >= 1, so 0 is invalid
    updates = {
        "uvicorn_workers": 0,
    }
    resp = client.post("/api/settings", json=updates, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400
    assert "worker counts must be >= 1" in resp.json()["detail"]
