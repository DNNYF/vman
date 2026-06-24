"""Audit event recording service (Milestone 1 / Task 7).

Every sensitive action in VMAN MUST emit an :class:`AuditEvent` row. This
service is the single write path for audit data; the table itself has no
update path (entries are append-only by convention).

Security notes
--------------
- ``metadata`` is passed through the redactor before persistence so
  leaked secrets in error messages or command output never reach the
  database in plaintext. The redactor is the same one used for log
  output, so audit and logs share a redaction policy.
- ``actor_type`` is constrained to the known set (``user``, ``system``,
  ``mcp``, ``cli``) -- a typo at the call site must not silently
  produce a malformed row.
- ``action`` is constrained to dotted tokens (letters, digits,
  underscores, dots, dashes) so log-style action names are stable and
  parseable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from vman.db import models
from vman.security.redaction import REDACTED, Redactor, default_redactor

_ACTION_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$")


class AuditService:
    """Append-only audit log writer + reader."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        redactor: Redactor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redactor = redactor or default_redactor()

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def record(
        self,
        *,
        actor_user_id: str | None = None,
        actor_type: str,
        action: str,
        resource_type: str,
        resource_id: str = "",
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> models.AuditEvent:
        """Append a new audit event and return the persisted row.

        ``metadata`` MUST be JSON-serialisable. ``actor_type`` MUST be
        one of the known values (raises ``ValueError`` otherwise).
        """
        if actor_type not in models.ACTOR_TYPES:
            raise ValueError(
                f"unknown actor_type: {actor_type!r}; must be one of {sorted(models.ACTOR_TYPES)}"
            )
        if not _ACTION_RE.match(action or ""):
            raise ValueError(
                f"invalid action: {action!r}; expected a dotted token like 'host.create'"
            )
        # Validate JSON-serialisability early.
        try:
            json.dumps(metadata or {})
        except (TypeError, ValueError) as exc:
            raise TypeError(f"metadata is not JSON-serialisable: {exc}") from exc

        redacted_meta = self._redact_metadata(metadata or {})

        with self._session_factory() as session:
            previous_hash = self._latest_event_hash(session)
            event = models.AuditEvent(
                id=uuid.uuid4().hex,
                actor_user_id=actor_user_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id or "",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata_json=redacted_meta,
                previous_hash=previous_hash,
                created_at=dt.datetime.now(dt.timezone.utc),
            )
            event.event_hash = self._event_hash(event)
            session.add(event)
            session.commit()
            session.refresh(event)
            session.expunge(event)
        return event

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        action_prefix: str | None = None,
        actor_user_id: str | None = None,
    ) -> list[models.AuditEvent]:
        """Return the most recent events, newest first."""
        stmt = select(models.AuditEvent).order_by(models.AuditEvent.created_at.desc())
        if action_prefix:
            stmt = stmt.where(models.AuditEvent.action.like(f"{action_prefix}%"))
        if actor_user_id:
            stmt = stmt.where(models.AuditEvent.actor_user_id == actor_user_id)
        stmt = stmt.limit(max(1, int(limit))).offset(max(0, int(offset)))
        with self._session_factory() as session:
            rows = session.execute(stmt).scalars().all()
            # Detach so the caller can iterate freely.
            for r in rows:
                session.expunge(r)
        return list(rows)

    def verify_hash_chain(self) -> bool:
        """Return True when stored audit hashes form an unbroken chain."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(models.AuditEvent).order_by(
                        models.AuditEvent.created_at.asc(),
                        models.AuditEvent.id.asc(),
                    )
                )
                .scalars()
                .all()
            )
            previous = ""
            for row in rows:
                if row.previous_hash != previous:
                    return False
                if row.event_hash != self._event_hash(row):
                    return False
                previous = row.event_hash
        return True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def register_secret_for_redaction(self, secret: str) -> None:
        """Teach the redactor about a plaintext secret that may appear
        in subsequent audit metadata (e.g. a credential that the
        audit event describes)."""
        self._redactor.register(secret)

    def _latest_event_hash(self, session) -> str:
        row = (
            session.execute(
                select(models.AuditEvent).order_by(
                    models.AuditEvent.created_at.desc(),
                    models.AuditEvent.id.desc(),
                )
            )
            .scalars()
            .first()
        )
        return row.event_hash if row is not None else ""

    def _event_hash(self, event: models.AuditEvent) -> str:
        payload = {
            "id": event.id,
            "actor_user_id": event.actor_user_id or "",
            "actor_type": event.actor_type,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id or "",
            "ip_address": event.ip_address or "",
            "user_agent": event.user_agent or "",
            "metadata_json": event.metadata_json or {},
            "previous_hash": event.previous_hash or "",
            "created_at": self._canonical_dt(event.created_at),
        }
        data = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def _canonical_dt(self, value: dt.datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat()

    def _redact_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in metadata.items():
            out[key] = self._redact_value(value)
        return out

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redactor.redact(value)
        if isinstance(value, dict):
            return {k: self._redact_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            redacted = [self._redact_value(v) for v in value]
            return type(value)(redacted)
        return value


__all__ = ["AuditService", "REDACTED"]
