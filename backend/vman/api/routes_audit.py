"""Audit list endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query

from vman.api.deps import CurrentUser
from vman.db.session import get_sessionmaker
from vman.security.audit import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _audit_service() -> AuditService:
    return AuditService(session_factory=get_sessionmaker())


@router.get("")
def list_audit(
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action_prefix: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
) -> list[dict]:
    """Return the most recent audit events, newest first.

    The response shape is deliberately minimal so we never accidentally
    surface secret-bearing metadata. Callers should fetch /api/audit
    only via authenticated, CSRF-protected browser code.
    """
    svc = _audit_service()
    rows = svc.list_recent(
        limit=limit,
        offset=offset,
        action_prefix=action_prefix,
        actor_user_id=actor_user_id,
    )
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "actor_user_id": r.actor_user_id,
                "actor_type": r.actor_type,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "metadata": r.metadata_json,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
        )
    return out


__all__ = ["router"]
