"""Integration tests for the job log SSE stream (Task 17)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from vman.config import get_settings
from vman.db import models
from vman.db.base import Base
from vman.db.session import get_sessionmaker, reset_engine
from vman.main import create_app
from vman.services.events import JobEventBroker
from vman.services.jobs import JobService


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
    # Stop any previously-running worker and start a fresh one against
    # the test DB.  We do NOT start the worker -- these tests want
    # deterministic control over log emission.
    from vman.main import reset_background_worker

    reset_background_worker()
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
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name="host-sse",
                hostname_or_ip="127.0.0.1",
                ssh_port=22,
                username="root",
                auth_method="key",
                created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
        )
    eng.dispose()
    return host_id


def _iter_sse_events(response, *, timeout: float = 4.0) -> Iterator[dict]:
    """Read raw SSE frames and yield parsed event dicts.

    The TestClient returns a streaming Response; we iterate its
    ``iter_lines`` and assemble ``event:`` / ``data:`` pairs into a
    dict.  We bail out if we go ``timeout`` seconds without a new
    line.
    """

    last_ts = time.time()
    pending_event: str | None = None
    pending_data: list[str] = []
    for line in response.iter_lines():
        last_ts = time.time()
        if not line:
            # Blank line -> end of frame.
            if pending_event and pending_data:
                payload = "\n".join(pending_data)
                try:
                    yield {"event": pending_event, "data": json.loads(payload)}
                except json.JSONDecodeError:
                    yield {"event": pending_event, "data": payload}
            pending_event = None
            pending_data = []
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        if decoded.startswith("event:"):
            pending_event = decoded.split(":", 1)[1].strip()
        elif decoded.startswith("data:"):
            pending_data.append(decoded.split(":", 1)[1].strip())
        elif decoded.startswith(":"):
            # Comment / keep-alive.
            continue
        if time.time() - last_ts > timeout:
            return


def test_sse_stream_returns_history_on_connect(client: TestClient, tmp_path) -> None:
    """A fresh subscriber sees the broker's history snapshot."""

    csrf = _setup_and_login(client)
    host_id = _seed_host(tmp_path / "vman.db")
    create_resp = client.post(
        "/api/jobs/command",
        json={"host_id": host_id, "command": "echo preloaded"},
        headers=_csrf(csrf),
    )
    job_id = create_resp.json()["id"]

    # The app has already published a status event for the create.
    # Add two log events to the same broker, then close the job so
    # the SSE generator sees a terminal status and exits.
    broker: JobEventBroker = client.app.state.events
    svc = JobService(session_factory=get_sessionmaker(), broker=broker)
    svc.append_log(job_id=job_id, stream="stdout", line="alpha")
    svc.append_log(job_id=job_id, stream="stdout", line="beta")
    svc.cancel(job_id=job_id, actor_user_id=None)

    with client.stream("GET", f"/api/jobs/{job_id}/logs/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = []
        for ev in _iter_sse_events(resp, timeout=3.0):
            events.append(ev)

    log_events = [e for e in events if e["event"] == "log"]
    assert len(log_events) >= 2
    assert log_events[0]["data"]["data"]["line_redacted"] == "alpha"
    assert log_events[1]["data"]["data"]["line_redacted"] == "beta"


def test_sse_stream_streams_live_events_then_closes_on_terminal(
    client: TestClient, tmp_path
) -> None:
    """A status event with a terminal status closes the stream."""

    csrf = _setup_and_login(client)
    host_id = _seed_host(tmp_path / "vman.db")
    create_resp = client.post(
        "/api/jobs/command",
        json={"host_id": host_id, "command": "echo hi"},
        headers=_csrf(csrf),
    )
    job_id = create_resp.json()["id"]

    broker: JobEventBroker = client.app.state.events

    def consume() -> list[dict]:
        events: list[dict] = []
        with client.stream("GET", f"/api/jobs/{job_id}/logs/stream") as resp:
            assert resp.status_code == 200
            for ev in _iter_sse_events(resp, timeout=5.0):
                events.append(ev)
                if ev.get("event") == "status" and (
                    ev["data"].get("data", {}).get("status") == "cancelled"
                ):
                    break
        return events

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    # Give the consumer time to subscribe before we publish.
    time.sleep(0.5)
    cancel = client.post(f"/api/jobs/{job_id}/cancel", headers=_csrf(csrf))
    assert cancel.status_code == 200
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "SSE stream did not close on terminal status"
    assert broker.subscriber_count(job_id) == 0


def test_sse_stream_redacts_lines(client: TestClient, tmp_path) -> None:
    """A registered secret MUST be redacted in the SSE stream."""

    from vman.security.redaction import default_redactor

    default_redactor().register("sse-secret-xyz")

    csrf = _setup_and_login(client)
    host_id = _seed_host(tmp_path / "vman.db")
    create_resp = client.post(
        "/api/jobs/command",
        json={"host_id": host_id, "command": "echo sse-secret-xyz"},
        headers=_csrf(csrf),
    )
    job_id = create_resp.json()["id"]

    broker: JobEventBroker = client.app.state.events
    svc = JobService(session_factory=get_sessionmaker(), broker=broker)
    svc.append_log(job_id=job_id, stream="stdout", line="echo sse-secret-xyz")
    # Push a terminal status to close the stream promptly.
    svc.cancel(job_id=job_id, actor_user_id=None)

    with client.stream("GET", f"/api/jobs/{job_id}/logs/stream") as resp:
        assert resp.status_code == 200
        leaked = False
        for ev in _iter_sse_events(resp, timeout=4.0):
            data = ev["data"]
            data_str = json.dumps(data) if isinstance(data, dict) else str(data)
            if "sse-secret-xyz" in data_str:
                leaked = True
                break
        assert not leaked, "secret leaked via SSE stream"


def test_sse_stream_returns_404_for_unknown_job(client: TestClient) -> None:
    _setup_and_login(client)
    resp = client.get("/api/jobs/does-not-exist/logs/stream")
    assert resp.status_code == 404
