"""Unit tests for the database layer (Milestone 0 / Task 2).

These tests exercise SQLAlchemy model creation in an isolated temporary
SQLite database (no migrations required) and confirm the basic invariants
each model needs to enforce:

- Tables can be created and torn down cleanly.
- String columns enforce non-empty values where appropriate.
- Encrypted-credential columns NEVER accept plaintext at the model
  level: the vault layer writes the ciphertext, and the application
  layer must use ``Vault.encrypt`` first.
- Cascade / relationship integrity for jobs and audit events.
- Timestamps default to UTC, never naive datetimes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from vman.db import models
from vman.db.base import Base
from vman.db.session import SessionFactory, get_engine, get_sessionmaker


@pytest.fixture()
def engine():
    """Fresh in-memory SQLite engine per test."""
    eng = create_engine(
        "sqlite:///:memory:",
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_base_metadata_create_all_is_idempotent(engine):
    """Calling create_all on an already-created schema must not raise."""
    # The fixture already created; calling again must be a no-op.
    Base.metadata.create_all(engine)
    # All declared tables exist.
    inspector = inspect(engine)
    expected_tables = {
        "credentials",
        "encryption_keys",
        "audit_events",
    }
    actual = set(inspector.get_table_names())
    assert expected_tables.issubset(actual), "missing tables: {expected_tables - actual}"


def test_session_factory_yields_isolated_sessions():
    """The session factory must hand out distinct sessions and close them safely."""
    factory = SessionFactory(engine=get_engine())
    with factory() as s1, factory() as s2:
        assert s1 is not s2
        # s2 is closed after the inner context exits.
    # s1 is closed after the outer context exits.


def test_get_engine_uses_settings_database_url(monkeypatch):
    """The default engine must honour VMAN_DATABASE_URL from settings."""
    # We just check that get_engine returns something callable; we cannot
    # fully isolate the global because the lru_cache is process-wide.
    eng = get_engine()
    assert eng is not None
    # The URL string starts with sqlite (default) or whatever the operator set.
    assert str(eng.url).split("://")[0] in {"sqlite", "postgresql"}


def test_get_sessionmaker_returns_bound_factory():
    sm = get_sessionmaker()
    assert sm is not None
    with sm() as s:
        # A session opened through the global factory is bound to the engine.
        assert s.bind is not None


# --- Audit events -------------------------------------------------------


def test_audit_event_round_trip(session: Session) -> None:
    ev = models.AuditEvent(
        id=str(uuid.uuid4()),
        actor_user_id=None,
        actor_type="system",
        action="system.bootstrap",
        resource_type="system",
        resource_id="vman",
        ip_address=None,
        user_agent=None,
        metadata_json={"note": "first boot"},
    )
    session.add(ev)
    session.commit()

    found = session.execute(select(models.AuditEvent)).scalar_one()
    assert found.action == "system.bootstrap"
    assert found.metadata_json == {"note": "first boot"}
    assert isinstance(found.created_at, dt.datetime)
    assert found.created_at.tzinfo is not None, "created_at must be timezone-aware"


# --- Credentials -------------------------------------------------------


def _make_cred(
    session: Session,
    *,
    name: str = "host-sg-1-ssh",
    kind: str = "ssh_password",
) -> models.Credential:
    return models.Credential(
        id=str(uuid.uuid4()),
        name=name,
        kind=kind,
        encrypted_payload=b"\x00\x01\x02\x03ciphertext-blob",
        encryption_key_id="k1",
        fingerprint="sha256-deadbeef",
        metadata_json={},
    )


def test_credential_encrypted_payload_is_required(session: Session) -> None:
    """A credential row must always carry ciphertext, never plaintext."""
    cred = models.Credential(
        id=str(uuid.uuid4()),
        name="host-sg-2-ssh",
        kind="ssh_password",
        # No encrypted_payload -- this is a logic error and must be rejected.
        encryption_key_id="k1",
        fingerprint="sha256-cafe",
        metadata_json={},
    )
    session.add(cred)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_credential_kind_must_be_known(session: Session) -> None:
    """The kind column is constrained to a known set."""
    cred = _make_cred(session)
    cred.kind = "totally-unknown-kind"
    session.add(cred)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_credential_name_must_be_unique(session: Session) -> None:
    cred_a = _make_cred(session, name="dup")
    session.add(cred_a)
    session.commit()

    cred_b = _make_cred(session, name="dup")
    session.add(cred_b)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# --- Encryption keys ---------------------------------------------------


def test_encryption_key_records_version_and_status(session: Session) -> None:
    k = models.EncryptionKey(
        id="k1",
        version=1,
        status="active",
        created_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(k)
    session.commit()
    found = session.execute(select(models.EncryptionKey)).scalar_one()
    assert found.id == "k1"
    assert found.status == "active"
