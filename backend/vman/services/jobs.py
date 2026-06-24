"""Job service (Milestone 3 / Task 11).

The job service is the only place that mutates the jobs / job_steps /
job_logs tables. The HTTP layer and the worker both go through this
service. The worker is intentionally separate (services/worker.py)
so the service has no implicit dependency on a background loop.

Security notes
--------------
- The service emits audit events on create / cancel / approve / deny
  / retry so every state change has a record.
- ``error_summary_redacted`` is run through the redactor before
  persistence so a leaked credential in a stack trace never reaches
  the DB in plaintext.
- The service never decrypts vault credentials; it only stores the
  reference and the worker handles decryption at run time.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from vman.db import models
from vman.security.audit import AuditService
from vman.security.policy import decision_for_command
from vman.security.redaction import default_redactor
from vman.services.events import JobEventBroker


class JobServiceError(Exception):
    """Domain-level job service failure."""


class JobNotFoundError(JobServiceError):
    pass


class JobConflictError(JobServiceError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _redact(s: str) -> str:
    return default_redactor().redact(s)


def _serialise_status(job: models.Job) -> dict[str, object]:
    """Render a job into the public dict shape used by SSE/UI."""

    return {
        "id": job.id,
        "status": job.status,
        "approval_status": job.approval_status,
        "exit_code": job.exit_code,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_summary_redacted": job.error_summary_redacted,
    }


class JobService:
    """CRUD + state transitions for jobs."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        audit: AuditService | None = None,
        broker: JobEventBroker | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit = audit or AuditService(
            session_factory=session_factory,
            redactor=default_redactor(),
        )
        self._broker = broker or JobEventBroker()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def get(self, job_id: str) -> models.Job | None:
        with self._session_factory() as session:
            row = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
        return row

    def list_jobs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        host_id: str | None = None,
        status: str | None = None,
    ) -> list[models.Job]:
        with self._session_factory() as session:
            stmt = select(models.Job).order_by(models.Job.created_at.desc())
            if host_id:
                stmt = stmt.where(models.Job.host_id == host_id)
            if status:
                stmt = stmt.where(models.Job.status == status)
            stmt = stmt.limit(max(1, int(limit))).offset(max(0, int(offset)))
            rows = session.execute(stmt).scalars().all()
            for r in rows:
                session.expunge(r)
        return list(rows)

    def list_logs(self, job_id: str, *, limit: int = 1000) -> list[models.JobLog]:
        with self._session_factory() as session:
            stmt = (
                select(models.JobLog)
                .where(models.JobLog.job_id == job_id)
                .order_by(models.JobLog.id.asc())
                .limit(max(1, int(limit)))
            )
            rows = session.execute(stmt).scalars().all()
            for r in rows:
                session.expunge(r)
        return list(rows)

    def list_steps(self, job_id: str) -> list[models.JobStep]:
        with self._session_factory() as session:
            stmt = (
                select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            rows = session.execute(stmt).scalars().all()
            for r in rows:
                session.expunge(r)
        return list(rows)

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def create_command(
        self,
        *,
        host_id: str,
        command: str,
        actor_user_id: str | None = None,
        timeout_seconds: int = 300,
        risk_level: str | None = None,
        approval_required: bool = False,
        idempotency_key: str | None = None,
        environment: str | None = None,
    ) -> models.Job:
        if not command or not command.strip():
            raise JobServiceError("command must be a non-empty string")
        if timeout_seconds < 1 or timeout_seconds > 86400:
            raise JobServiceError("timeout_seconds out of range")
        if idempotency_key:
            with self._session_factory() as session:
                existing = session.execute(
                    select(models.Job).where(models.Job.idempotency_key == idempotency_key)
                ).scalar_one_or_none()
                if existing is not None:
                    session.expunge(existing)
                    return existing

        # Look up the host's environment for the policy decision.
        env = environment
        if env is None:
            with self._session_factory() as session:
                host_row = session.execute(
                    select(models.Host).where(models.Host.id == host_id)
                ).scalar_one_or_none()
                if host_row is not None:
                    env = host_row.environment
                    session.expunge(host_row)
        env = env or "experiment"

        # Compute the policy decision. An explicit ``approval_required``
        # from the caller OR a decision-level requirement forces the
        # job into the pending state.
        decision = decision_for_command(command, environment=env, risk_level=risk_level)
        if decision.blocked:
            raise JobServiceError(f"command blocked by policy: {decision.reason}")
        computed_risk = decision.risk_level.value
        approval_status = (
            "pending" if (approval_required or decision.approval_required) else "not_required"
        )
        now = _now()
        job = models.Job(
            id=uuid.uuid4().hex,
            host_id=host_id,
            command_summary=command[:2048],
            requested_by_user_id=actor_user_id,
            status="queued",
            risk_level=computed_risk,
            approval_status=approval_status,
            approval_requested_at=now if approval_required else None,
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            session.expunge(job)
        self._audit.record(
            actor_user_id=actor_user_id,
            actor_type="user",
            action="job.create",
            resource_type="job",
            resource_id=job.id,
            metadata={
                "host_id": host_id,
                "command_summary": _redact(job.command_summary),
                "risk_level": risk_level,
                "approval_status": approval_status,
                "timeout_seconds": timeout_seconds,
            },
        )
        self._broker.publish(
            "status",
            job.id,
            _serialise_status(job),
        )
        return job

    def cancel(
        self,
        *,
        job_id: str,
        actor_user_id: str | None = None,
    ) -> models.Job:
        with self._session_factory() as session:
            row = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if row is None:
                raise JobNotFoundError(f"job not found: {job_id}")
            if row.status in {"success", "failed", "cancelled", "denied"}:
                # Idempotent cancel.
                session.expunge(row)
                return row
            row.status = "cancelled"
            row.finished_at = _now()
            row.updated_at = row.finished_at
            session.commit()
            session.refresh(row)
            session.expunge(row)
            job = row
        self._audit.record(
            actor_user_id=actor_user_id,
            actor_type="user",
            action="job.cancel",
            resource_type="job",
            resource_id=job.id,
        )
        self._broker.publish(
            "status",
            job.id,
            _serialise_status(job),
        )
        return job

    def retry(
        self,
        *,
        job_id: str,
        actor_user_id: str | None = None,
    ) -> models.Job:
        with self._session_factory() as session:
            original = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if original is None:
                raise JobNotFoundError(f"job not found: {job_id}")
            if original.status not in {"success", "failed", "cancelled"}:
                raise JobConflictError(
                    f"job {job_id} is still in state {original.status}; "
                    "wait for it to terminate before retrying"
                )
            # Detach the original before creating the new row.
            session.expunge(original)
        new_job = self.create_command(
            host_id=original.host_id or "",
            command=original.command_summary,
            actor_user_id=actor_user_id,
            timeout_seconds=original.timeout_seconds,
            risk_level=original.risk_level,
            approval_required=original.approval_status == "pending",
        )
        return new_job

    def approve(
        self,
        *,
        job_id: str,
        actor_user_id: str | None = None,
    ) -> models.Job:
        with self._session_factory() as session:
            row = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if row is None:
                raise JobNotFoundError(f"job not found: {job_id}")
            if row.approval_status not in {"pending"}:
                raise JobConflictError(f"job {job_id} is not pending approval")
            now = _now()
            row.approval_status = "approved"
            row.approved_by_user_id = actor_user_id
            row.approved_at = now
            row.updated_at = now
            session.commit()
            session.refresh(row)
            session.expunge(row)
            job = row
        self._audit.record(
            actor_user_id=actor_user_id,
            actor_type="user",
            action="job.approve",
            resource_type="job",
            resource_id=job.id,
        )
        self._broker.publish(
            "status",
            job.id,
            _serialise_status(job),
        )
        return job

    def deny(
        self,
        *,
        job_id: str,
        actor_user_id: str | None = None,
        reason: str | None = None,
    ) -> models.Job:
        with self._session_factory() as session:
            row = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if row is None:
                raise JobNotFoundError(f"job not found: {job_id}")
            if row.approval_status not in {"pending"}:
                raise JobConflictError(f"job {job_id} is not pending approval")
            now = _now()
            row.approval_status = "denied"
            row.status = "denied"
            row.finished_at = now
            row.error_summary_redacted = _redact(reason or "denied")
            row.updated_at = now
            session.commit()
            session.refresh(row)
            session.expunge(row)
            job = row
        self._audit.record(
            actor_user_id=actor_user_id,
            actor_type="user",
            action="job.deny",
            resource_type="job",
            resource_id=job.id,
            metadata={"reason": _redact(reason or "") or None},
        )
        self._broker.publish(
            "status",
            job.id,
            _serialise_status(job),
        )
        return job

    # ------------------------------------------------------------------ #
    # Worker-facing state transitions
    # ------------------------------------------------------------------ #

    def claim_next_queued(self) -> models.Job | None:
        """Atomically claim the oldest queued+approved job, if any."""
        with self._session_factory() as session:
            stmt = (
                select(models.Job)
                .where(models.Job.status == "queued")
                .where(models.Job.approval_status.in_(["not_required", "approved"]))
                .order_by(models.Job.created_at.asc())
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.started_at = _now()
            row.updated_at = row.started_at
            session.commit()
            session.refresh(row)
            session.expunge(row)
        self._broker.publish(
            "status",
            row.id,
            _serialise_status(row),
        )
        return row

    def complete(
        self,
        *,
        job_id: str,
        exit_code: int,
        error_summary: str | None = None,
    ) -> models.Job:
        with self._session_factory() as session:
            row = session.execute(
                select(models.Job).where(models.Job.id == job_id)
            ).scalar_one_or_none()
            if row is None:
                raise JobNotFoundError(f"job not found: {job_id}")
            now = _now()
            row.exit_code = exit_code
            row.status = "success" if exit_code == 0 else "failed"
            row.finished_at = now
            row.updated_at = now
            if error_summary:
                row.error_summary_redacted = _redact(error_summary)
            session.commit()
            session.refresh(row)
            session.expunge(row)
        self._broker.publish(
            "status",
            row.id,
            _serialise_status(row),
        )
        return row

    def append_log(
        self,
        *,
        job_id: str,
        stream: str,
        line: str,
        step_id: str | None = None,
    ) -> models.JobLog:
        redacted = _redact(line)
        import hashlib

        line_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
        with self._session_factory() as session:
            entry = models.JobLog(
                job_id=job_id,
                step_id=step_id,
                stream=stream,
                line_redacted=redacted,
                line_hash=line_hash,
                timestamp=_now(),
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            session.expunge(entry)
        # Publish the redacted line.  We deliberately publish AFTER the
        # DB commit so a subscriber that loads the log list later sees
        # the same content the broker delivered.  The line_redacted
        # field is what is shown to operators; the broker re-redacts
        # for defence-in-depth in case a caller accidentally passes a
        # raw line.
        self._broker.publish(
            "log",
            job_id,
            {
                "id": entry.id,
                "stream": entry.stream,
                "line_redacted": entry.line_redacted,
                "line_hash": entry.line_hash,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
            },
        )
        return entry


__all__ = [
    "JobConflictError",
    "JobNotFoundError",
    "JobService",
    "JobServiceError",
]
