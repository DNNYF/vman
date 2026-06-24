"""Job HTTP routes (Milestone 3 / Task 11 + Task 17)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from vman.api.deps import CurrentUser
from vman.db import models
from vman.db.session import get_sessionmaker
from vman.security.csrf import require_csrf
from vman.security.redaction import default_redactor
from vman.services.events import JobEvent, JobEventBroker
from vman.services.jobs import (
    JobConflictError,
    JobNotFoundError,
    JobService,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# --------------------------------------------------------------------------- #
# Service + broker helpers
# --------------------------------------------------------------------------- #


def _broker(request: Request) -> JobEventBroker:
    """Resolve the in-process event broker from the FastAPI app."""

    broker = getattr(request.app.state, "events", None)
    if broker is None:
        broker = JobEventBroker()
    return broker


def _service(request: Request) -> JobService:
    """Build a JobService that shares the app's event broker.

    The broker lives on ``app.state.events``; we wire it into the
    service so every state transition lands on the same topic the SSE
    stream is reading from.
    """
    return JobService(
        session_factory=get_sessionmaker(),
        broker=_broker(request),
    )


def _job_to_out(job: models.Job) -> dict:
    return {
        "id": job.id,
        "host_id": job.host_id,
        "recipe_name": job.recipe_name,
        "command_summary": job.command_summary,
        "requested_by_user_id": job.requested_by_user_id,
        "status": job.status,
        "risk_level": job.risk_level,
        "approval_status": job.approval_status,
        "approval_requested_at": (
            job.approval_requested_at.isoformat() if job.approval_requested_at else None
        ),
        "approved_by_user_id": job.approved_by_user_id,
        "approved_at": (job.approved_at.isoformat() if job.approved_at else None),
        "started_at": (job.started_at.isoformat() if job.started_at else None),
        "finished_at": (job.finished_at.isoformat() if job.finished_at else None),
        "timeout_seconds": job.timeout_seconds,
        "exit_code": job.exit_code,
        "error_summary_redacted": job.error_summary_redacted,
        "idempotency_key": job.idempotency_key,
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "updated_at": job.updated_at.isoformat() if job.updated_at else "",
    }


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class CommandJobCreate(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=64)
    command: str = Field(..., min_length=1, max_length=2048)
    timeout_seconds: int = Field(300, ge=1, le=86400)
    risk_level: str | None = Field(default=None, max_length=16)
    approval_required: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)


class DenyPayload(BaseModel):
    reason: str = Field("", max_length=2048)


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #


@router.get("")
def list_jobs(
    request: Request,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    host_id: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict]:
    rows = _service(request).list_jobs(
        limit=limit, offset=offset, host_id=host_id, status=status_filter
    )
    return [_job_to_out(r) for r in rows]


# --------------------------------------------------------------------------- #
# Get
# --------------------------------------------------------------------------- #


@router.get("/{job_id}")
def get_job(request: Request, job_id: str, user: CurrentUser) -> dict:
    svc = _service(request)
    job = svc.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    out = _job_to_out(job)
    out["logs"] = [
        {
            "id": log.id,
            "stream": log.stream,
            "line_redacted": log.line_redacted,
            "line_hash": log.line_hash,
            "timestamp": log.timestamp.isoformat() if log.timestamp else "",
        }
        for log in svc.list_logs(job.id, limit=500)
    ]
    return out


@router.get("/{job_id}/logs")
def get_job_logs(
    request: Request,
    job_id: str,
    user: CurrentUser,
    limit: int = Query(1000, ge=1, le=5000),
) -> list[dict]:
    svc = _service(request)
    job = svc.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return [
        {
            "id": log.id,
            "stream": log.stream,
            "line_redacted": log.line_redacted,
            "line_hash": log.line_hash,
            "timestamp": log.timestamp.isoformat() if log.timestamp else "",
        }
        for log in svc.list_logs(job_id, limit=limit)
    ]


# --------------------------------------------------------------------------- #
# SSE log stream (Task 17)
# --------------------------------------------------------------------------- #

# Re-applied on every event so a future code path that forgets to
# redact cannot leak a secret to a logged-in user.
_REDACTOR = default_redactor()


def _terminal_statuses() -> set[str]:
    return {"success", "failed", "cancelled", "denied"}


def _log_event_to_sse(event: JobEvent) -> str:
    """Re-render a ``log`` event with defence-in-depth redaction."""

    data = dict(event.data)
    line = data.get("line_redacted")
    if isinstance(line, str) and line:
        data["line_redacted"] = _REDACTOR.redact(line)
    payload = {
        "kind": event.kind,
        "job_id": event.job_id,
        "seq": event.seq,
        "timestamp": event.timestamp,
        "data": data,
    }
    body = json.dumps(payload, separators=(",", ":"))
    safe = body.replace("\r", "\\r").replace("\n", "\\n")
    return f"event: {event.kind}\nid: {event.seq}\ndata: {safe}\n\n"


def _status_event_to_sse(event: JobEvent) -> str:
    payload = {
        "kind": event.kind,
        "job_id": event.job_id,
        "seq": event.seq,
        "timestamp": event.timestamp,
        "data": event.data,
    }
    body = json.dumps(payload, separators=(",", ":"))
    safe = body.replace("\r", "\\r").replace("\n", "\\n")
    return f"event: {event.kind}\nid: {event.seq}\ndata: {safe}\n\n"


def _heartbeat_frame() -> str:
    """An SSE comment frame: keeps the connection open through proxies
    that drop idle sockets after 30-60 seconds."""

    return ": ping\n\n"


async def _sse_log_stream(
    request: Request,
    broker: JobEventBroker,
    job_id: str,
) -> AsyncIterator[bytes]:
    """Yield SSE-encoded log + status events for ``job_id``.

    The generator subscribes to the broker once and reads events
    forever (with periodic heartbeats) until the job reaches a
    terminal status, the client disconnects, or the broker is shut
    down.
    """

    history, queue = broker.subscribe(job_id)
    try:
        # Track the highest log id / status seq we have emitted so a
        # reconnecting client could use the broker history to backfill.
        last_status_seq = 0
        for ev in history:
            if ev.kind == "log":
                yield _log_event_to_sse(ev).encode("utf-8")
            elif ev.kind == "status":
                yield _status_event_to_sse(ev).encode("utf-8")
                last_status_seq = ev.seq
                if isinstance(ev.data, dict) and ev.data.get("status") in _terminal_statuses():
                    return

        heartbeat_interval = 15.0
        last_heartbeat = asyncio.get_event_loop().time()
        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield _heartbeat_frame().encode("utf-8")
                    last_heartbeat = now
                continue
            if event is None:
                return
            if event.kind == "log":
                yield _log_event_to_sse(event).encode("utf-8")
            else:
                yield _status_event_to_sse(event).encode("utf-8")
                if event.seq > last_status_seq:
                    last_status_seq = event.seq
                if (
                    isinstance(event.data, dict)
                    and event.data.get("status") in _terminal_statuses()
                ):
                    return
    finally:
        broker.unsubscribe(job_id, queue)


@router.get("/{job_id}/logs/stream")
async def stream_job_logs(
    request: Request,
    job_id: str,
    user: CurrentUser,
) -> StreamingResponse:
    """Server-Sent Events stream of redacted log lines + status updates.

    The stream is authenticated (session cookie).  The CSRF token is
    NOT required for GET, matching the other read endpoints.

    Frames:
      - ``event: log``     -> one redacted log line
      - ``event: status``  -> one job status snapshot
      - ``event: heartbeat`` (comment) -> keep-alive

    The stream closes when the job reaches a terminal status or the
    client disconnects.
    """

    svc = _service(request)
    job = svc.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    broker = _broker(request)

    async def event_source() -> AsyncIterator[bytes]:
        async for chunk in _sse_log_stream(request, broker, job_id):
            yield chunk

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",  # nginx hint to disable buffering
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #


@router.post("/command", status_code=status.HTTP_201_CREATED)
def create_command_job(
    request: Request,
    payload: CommandJobCreate,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict:
    job = _service(request).create_command(
        host_id=payload.host_id,
        command=payload.command,
        actor_user_id=user.id,
        timeout_seconds=payload.timeout_seconds,
        risk_level=payload.risk_level,
        approval_required=payload.approval_required,
        idempotency_key=payload.idempotency_key,
    )
    return _job_to_out(job)


# --------------------------------------------------------------------------- #
# Cancel / retry
# --------------------------------------------------------------------------- #


@router.post("/{job_id}/cancel")
def cancel_job(
    request: Request,
    job_id: str,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict:
    try:
        job = _service(request).cancel(job_id=job_id, actor_user_id=user.id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _job_to_out(job)


@router.post("/{job_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_job(
    request: Request,
    job_id: str,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict:
    try:
        job = _service(request).retry(job_id=job_id, actor_user_id=user.id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_to_out(job)


# --------------------------------------------------------------------------- #
# Approve / deny
# --------------------------------------------------------------------------- #


@router.post("/{job_id}/approve")
def approve_job(
    request: Request,
    job_id: str,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict:
    try:
        job = _service(request).approve(job_id=job_id, actor_user_id=user.id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_to_out(job)


@router.post("/{job_id}/deny")
def deny_job(
    request: Request,
    job_id: str,
    payload: DenyPayload,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict:
    try:
        job = _service(request).deny(
            job_id=job_id,
            actor_user_id=user.id,
            reason=payload.reason,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_to_out(job)


__all__ = ["router"]
