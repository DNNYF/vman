"""Integration tests for the Interactive SSH Terminal WebSocket endpoint."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from vman.config import get_settings
from vman.db.session import reset_engine
from vman.main import create_app


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


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def test_terminal_unauthenticated_rejects(client: TestClient) -> None:
    # Attempting to open a websocket connection without login should be rejected
    with pytest.raises(Exception):
        with client.websocket_connect("/api/terminal/ws/some-host-id") as ws:
            pass


@patch("paramiko.SSHClient")
def test_terminal_authenticated_succeeds(mock_ssh_client_cls, client: TestClient) -> None:
    # Setup mock SSHClient
    mock_client = MagicMock()
    mock_ssh_client_cls.return_value = mock_client
    mock_channel = MagicMock()
    mock_client.invoke_shell.return_value = mock_channel
    
    # script channel.recv to return some data then block/empty
    mock_channel.recv.side_effect = [b"welcome to vps\n", b""]

    csrf = _setup_and_login(client)

    # First, create a host in the DB
    resp = client.post(
        "/api/hosts",
        json={
            "name": "my-vps",
            "hostname_or_ip": "127.0.0.1",
            "ssh_port": 22,
            "username": "root",
            "auth_method": "password",
        },
        headers=_csrf_headers(csrf),
    )
    assert resp.status_code == 201
    host_id = resp.json()["id"]

    # Connect via WebSocket
    with client.websocket_connect(f"/api/terminal/ws/{host_id}") as ws:
        # Receive welcoming messages
        msg = ws.receive_text()
        assert "welcome to vps" in msg
        
        # Send data
        ws.send_text("ls\n")
        
        # Verify that mock_channel.send was called
        # Wait a tiny bit since threads run concurrently
        for _ in range(20):
            if mock_channel.send.called:
                break
            time.sleep(0.05)
        
        assert mock_channel.send.called
