"""Integration tests for the Agent Bridge API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from vman.config import get_settings
from vman.db import models
from vman.db.base import Base
from vman.db.session import reset_engine, get_sessionmaker
from vman.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]

    import vman.db.models  # noqa: F401

    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    yield TestClient(create_app())
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


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def _seed_agents() -> None:
    session_factory = get_sessionmaker()
    with session_factory() as session:
        a1 = models.Agent(
            id="openclaw",
            name="OpenClaw MCP",
            status="setup_required",
            dns_status="off",
            domains=["api.anthropic.com"],
        )
        a2 = models.Agent(
            id="claudecode",
            name="Claude Code",
            status="active",
            dns_status="on",
            domains=["api.anthropic.com"],
        )
        session.add_all([a1, a2])
        session.commit()


def test_list_agents_unauthenticated_returns_401(client: TestClient) -> None:
    resp = client.get("/api/agents")
    assert resp.status_code == 401


def test_list_agents_succeeds(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    _seed_agents()

    resp = client.get("/api/agents", headers=_csrf_headers(csrf))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    
    body_by_id = {b["id"]: b for b in body}
    assert "openclaw" in body_by_id
    assert body_by_id["openclaw"]["name"] == "OpenClaw MCP"
    assert body_by_id["openclaw"]["status"] == "setup_required"
    assert body_by_id["openclaw"]["dns_status"] == "off"
    assert body_by_id["openclaw"]["domains"] == ["api.anthropic.com"]

    assert "claudecode" in body_by_id
    assert body_by_id["claudecode"]["name"] == "Claude Code"
    assert body_by_id["claudecode"]["status"] == "active"
    assert body_by_id["claudecode"]["dns_status"] == "on"


def test_toggle_dns_requires_csrf(client: TestClient) -> None:
    _setup_and_login(client)
    _seed_agents()

    resp = client.post("/api/agents/openclaw/toggle-dns")
    assert resp.status_code == 403  # CSRF missing


def test_toggle_dns_succeeds(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    _seed_agents()

    # Toggle from off to on
    resp = client.post("/api/agents/openclaw/toggle-dns", headers=_csrf_headers(csrf))
    assert resp.status_code == 200
    body = resp.json()
    assert body["dns_status"] == "on"

    # Toggle back from on to off
    resp = client.post("/api/agents/openclaw/toggle-dns", headers=_csrf_headers(csrf))
    assert resp.status_code == 200
    body = resp.json()
    assert body["dns_status"] == "off"


def test_toggle_dns_nonexistent_returns_404(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.post("/api/agents/missing-agent/toggle-dns", headers=_csrf_headers(csrf))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Agent not found"


def test_setup_agent_succeeds(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    _seed_agents()

    resp = client.post("/api/agents/openclaw/setup", headers=_csrf_headers(csrf))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"


def test_setup_agent_nonexistent_returns_404(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.post("/api/agents/missing-agent/setup", headers=_csrf_headers(csrf))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Agent not found"
