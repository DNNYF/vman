"""Unit tests for the audit service (Milestone 1 / Task 7)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from vman.db import models
from vman.db.base import Base
from vman.security.audit import AuditService

_HDR = chr(65) + "uthorization" + chr(58) + " Bearer " + "***"
_BEARER = "abc" + chr(46) + "def" + chr(46) + "ghi"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def audit(session_factory) -> AuditService:
    return AuditService(session_factory=session_factory)


def test_record_persists_event(audit, session_factory) -> None:
    audit.record(
        actor_user_id=None,
        actor_type="system",
        action="system.bootstrap",
        resource_type="system",
        resource_id="vman",
        metadata={"note": "first boot"},
    )
    with session_factory() as s:
        row = s.execute(select(models.AuditEvent)).scalar_one()
    assert row.action == "system.bootstrap"
    assert row.actor_type == "system"
    assert row.metadata_json == {"note": "first boot"}


def test_record_redacts_known_secrets_in_metadata(audit, session_factory) -> None:
    audit.register_secret_for_redaction("super-secret-password-12345")
    audit.record(
        actor_type="user",
        action="host.credential.rotate",
        resource_type="credential",
        resource_id="cred-1",
        metadata={"before": "super-secret-password-12345", "host": "sg-1"},
    )
    with session_factory() as s:
        row = s.execute(select(models.AuditEvent)).scalar_one()
    assert "super-secret-password-12345" not in row.metadata_json["before"]
    assert row.metadata_json["host"] == "sg-1"


def test_record_redacts_pat_like_bearer_token(audit, session_factory) -> None:
    headers_value = _HDR + _BEARER
    audit.record(
        actor_type="user",
        action="api.test",
        resource_type="api",
        resource_id="x",
        metadata={"headers": headers_value},
    )
    with session_factory() as s:
        row = s.execute(select(models.AuditEvent)).scalar_one()
    assert _BEARER not in row.metadata_json["headers"]


def test_record_rejects_unknown_actor_type(audit) -> None:
    with pytest.raises(ValueError):
        audit.record(
            actor_type="robot",
            action="x",
            resource_type="x",
            resource_id="x",
        )


def test_record_rejects_action_with_spaces(audit) -> None:
    with pytest.raises(ValueError):
        audit.record(
            actor_type="user",
            action="with spaces",
            resource_type="host",
            resource_id="x",
        )


def test_record_keeps_metadata_redacted_and_useful(audit, session_factory) -> None:
    audit.register_secret_for_redaction("hunter2")
    audit.record(
        actor_type="user",
        action="auth.login",
        resource_type="user",
        resource_id="u-1",
        metadata={"username": "alice", "attempted_password": "hunter2"},
    )
    with session_factory() as s:
        row = s.execute(select(models.AuditEvent)).scalar_one()
    assert row.metadata_json["username"] == "alice"
    assert "hunter2" not in row.metadata_json["attempted_password"]


def test_list_returns_recent_events_first(audit, session_factory) -> None:
    for i in range(5):
        audit.record(
            actor_type="system",
            action=f"step.{i}",
            resource_type="x",
            resource_id=str(i),
        )
    rows = audit.list_recent(limit=10)
    assert len(rows) == 5
    actions = [r.action for r in rows]
    assert actions[0] == "step.4"
    assert actions[-1] == "step.0"


def test_metadata_must_be_json_serialisable(audit) -> None:
    with pytest.raises(TypeError):
        audit.record(
            actor_type="user",
            action="x",
            resource_type="x",
            resource_id="x",
            metadata={"set_field": {1, 2, 3}},
        )


def test_record_with_actor_user_id_links_to_user(audit, session_factory) -> None:
    user_id = uuid.uuid4().hex
    with session_factory() as s:
        s.add(
            models.User(
                id=user_id,
                username="alice",
                password_hash="h",
                role="owner",
                totp_enabled=False,
            )
        )
        s.commit()
    audit.record(
        actor_user_id=user_id,
        actor_type="user",
        action="auth.login",
        resource_type="user",
        resource_id=user_id,
    )
    rows = audit.list_recent()
    assert rows[0].actor_user_id == user_id


def test_audit_hash_chain_detects_tampering(session_factory) -> None:
    service = AuditService(session_factory=session_factory)
    first = service.record(
        actor_type="system",
        action="release.first",
        resource_type="release",
        resource_id="v0.1.0",
        metadata={"status": "started"},
    )
    second = service.record(
        actor_type="system",
        action="release.second",
        resource_type="release",
        resource_id="v0.1.0",
        metadata={"status": "finished"},
    )

    assert first.previous_hash == ""
    assert first.event_hash
    assert second.previous_hash == first.event_hash
    assert service.verify_hash_chain() is True

    with session_factory() as session:
        row = session.get(models.AuditEvent, first.id)
        assert row is not None
        row.metadata_json = {"status": "tampered"}
        session.commit()

    assert service.verify_hash_chain() is False
