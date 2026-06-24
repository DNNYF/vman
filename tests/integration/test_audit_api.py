"""Integration tests for the audit API (Milestone 1 / Task 7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vman.config import get_settings
from vman.db.session import reset_engine
from vman.main import create_app

_HDR = "Authorization: Bearer "
_BEARER = "abc.def.ghi"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

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


def test_login_creates_audit_event(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.get("/api/audit", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    events = resp.json()
    actions = [e["action"] for e in events]
    assert "auth.setup" in actions
    assert any(a.endswith("login.success") or a.endswith("login.failure") for a in actions)


def test_logout_creates_audit_event(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "S3cret-passphrase!!"},
    )
    csrf = client.cookies.get("vman_csrf") or ""
    resp = client.get("/api/audit", headers={"X-CSRF-Token": csrf})
    actions = [e["action"] for e in resp.json()]
    assert "auth.logout" in actions


def test_failed_login_creates_audit_event(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "alice", "password": "S3cret-passphrase!!"},
    )
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "S3cret-passphrase!!"},
    )
    csrf = client.cookies.get("vman_csrf") or ""
    resp = client.get("/api/audit", headers={"X-CSRF-Token": csrf})
    actions = [e["action"] for e in resp.json()]
    assert any(a.endswith("login.failure") for a in actions)


def test_audit_response_does_not_leak_metadata_secrets(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    from vman.db.session import get_sessionmaker
    from vman.security.audit import AuditService
    from vman.security.redaction import default_redactor

    audit = AuditService(
        session_factory=get_sessionmaker(),
        redactor=default_redactor(),
    )
    audit.register_secret_for_redaction("topsecret-credential-xyz")
    audit.record(
        actor_type="user",
        action="host.credential.set",
        resource_type="host",
        resource_id="h-1",
        metadata={"value": "topsecret-credential-xyz"},
    )
    resp = client.get("/api/audit", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert "topsecret-credential-xyz" not in resp.text


def test_audit_list_is_paginated(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    resp = client.get("/api/audit?limit=2", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


def test_audit_requires_authentication(client: TestClient) -> None:
    resp = client.get("/api/audit")
    assert resp.status_code == 401


def test_audit_redacts_response_metadata(client: TestClient) -> None:
    csrf = _setup_and_login(client)
    from vman.db.session import get_sessionmaker
    from vman.security.audit import AuditService

    audit = AuditService(session_factory=get_sessionmaker())
    header_value = _HDR + _BEARER
    audit.record(
        actor_type="user",
        action="api.call",
        resource_type="api",
        resource_id="x",
        metadata={"header": header_value},
    )
    resp = client.get("/api/audit", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert _BEARER not in resp.text
