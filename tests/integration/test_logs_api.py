"""Integration tests for the system logs API endpoint (Phase 2)."""

from __future__ import annotations

import logging
import pytest
from fastapi.testclient import TestClient

from vman.config import get_settings
from vman.db.session import reset_engine
from vman.main import create_app
from vman.api.routes_logs import log_handler


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


def test_get_logs_succeeds(client: TestClient) -> None:
    csrf = _setup_and_login(client)

    logger = logging.getLogger("vman")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        # Trigger some test logs to ensure they are captured
        logger.info("Test log message for testing logs API")
        logger.warning("Test warning message for testing logs API")
    finally:
        logger.setLevel(old_level)

    # Fetch logs
    resp = client.get("/api/logs", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)

    # Check if the logs contains our triggered messages
    messages = [log["message"] for log in body]
    assert any("Test log message for testing logs API" in msg for msg in messages)
    assert any("Test warning message for testing logs API" in msg for msg in messages)


def test_get_logs_filtering_level(client: TestClient) -> None:
    csrf = _setup_and_login(client)

    # Clear buffer for test predictability
    log_handler.buffer.clear()

    logger = logging.getLogger("vman")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.info("Info log message")
        logger.error("Error log message")
    finally:
        logger.setLevel(old_level)

    # Fetch info logs only
    resp = client.get("/api/logs?level=info", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    levels = {log["level"] for log in body}
    assert "INFO" in levels
    assert "ERROR" not in levels


def test_get_logs_filtering_search(client: TestClient) -> None:
    csrf = _setup_and_login(client)

    # Clear buffer for test predictability
    log_handler.buffer.clear()

    logger = logging.getLogger("vman")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.info("Apple pie recipe")
        logger.info("Banana bread recipe")
    finally:
        logger.setLevel(old_level)

    # Search for apple
    resp = client.get("/api/logs?search=apple", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert "Apple pie recipe" in body[0]["message"]
