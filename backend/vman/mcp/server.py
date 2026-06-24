"""FastMCP server exposing safe VMAN fleet-management tools."""

from __future__ import annotations

import datetime as dt
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from vman.db import models
from vman.db.session import get_sessionmaker
from vman.security.policy import RiskLevel, decision_for_recipe
from vman.security.redaction import default_redactor
from vman.services.jobs import JobService
from vman.services.recipe_engine import (
    RecipeEngine,
    RecipeNotFoundError,
    RecipeSchemaError,
    get_builtin_recipe_summary,
    list_builtin_recipes,
    parse_recipe_text,
)

MCP_ACTOR_USER_ID = "mcp"
_HIGH_RISK_LEVELS = {RiskLevel.HIGH, RiskLevel.CRITICAL}
_REDACTOR = default_redactor()


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _safe_text(value: object) -> str:
    return _REDACTOR.redact(str(value or ""))


def _host_to_dict(host: models.Host) -> dict[str, object]:
    """Return non-secret host fields only."""
    return {
        "id": host.id,
        "name": _safe_text(host.name),
        "hostname_or_ip": _safe_text(host.hostname_or_ip),
        "ssh_port": host.ssh_port,
        "username": _safe_text(host.username),
        "auth_method": host.auth_method,
        "sudo_mode": host.sudo_mode,
        "environment": host.environment,
        "risk_level": host.risk_level,
        "tags": list(host.tags or []),
        "os_family": host.os_family,
        "os_name": host.os_name,
        "os_version": host.os_version,
        "package_manager": host.package_manager,
        "arch": host.arch,
        "cpu_cores": host.cpu_cores,
        "ram_mb": host.ram_mb,
        "disk_total_mb": host.disk_total_mb,
        "provider": host.provider,
        "region": host.region,
        "last_seen_at": _iso(host.last_seen_at),
        "disabled_at": _iso(host.disabled_at),
        "created_at": _iso(host.created_at),
        "updated_at": _iso(host.updated_at),
        "host_key_pinned": bool(host.host_key_fingerprint),
    }


def _job_to_dict(job: models.Job) -> dict[str, object]:
    return {
        "id": job.id,
        "host_id": job.host_id,
        "recipe_name": job.recipe_name,
        "command_summary": _safe_text(job.command_summary),
        "status": job.status,
        "risk_level": job.risk_level,
        "approval_status": job.approval_status,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "timeout_seconds": job.timeout_seconds,
        "exit_code": job.exit_code,
        "error_summary_redacted": _safe_text(job.error_summary_redacted),
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }


def _log_to_dict(log: models.JobLog) -> dict[str, object]:
    return {
        "id": log.id,
        "stream": log.stream,
        "line": _safe_text(log.line_redacted),
        "timestamp": _iso(log.timestamp),
    }


def _step_to_dict(step: models.JobStep) -> dict[str, object]:
    return {
        "id": step.id,
        "step_index": step.step_index,
        "name": _safe_text(step.name),
        "status": step.status,
        "started_at": _iso(step.started_at),
        "finished_at": _iso(step.finished_at),
        "exit_code": step.exit_code,
        "error_summary_redacted": _safe_text(step.error_summary_redacted),
    }


def _get_host_environment(host_id: str) -> str:
    with get_sessionmaker()() as session:
        host = session.execute(
            select(models.Host).where(models.Host.id == host_id)
        ).scalar_one_or_none()
        if host is None:
            raise ValueError(f"host not found: {host_id}")
        return str(host.environment or "experiment")


def _mcp_runner_factory(host: models.Host) -> Any:
    """Test seam for injecting a fake runner factory."""
    raise RuntimeError("default MCP runner factory should not be called directly")


_DEFAULT_RUNNER_FACTORY = _mcp_runner_factory


def _recipe_engine() -> RecipeEngine:
    if _mcp_runner_factory is _DEFAULT_RUNNER_FACTORY:
        return RecipeEngine(session_factory=get_sessionmaker())
    return RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=_mcp_runner_factory,
    )


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(
        "vman",
        instructions=(
            "Safe VMAN tools for listing hosts, recipes, jobs, and running "
            "approved low-risk built-in recipes. High-risk recipes return "
            "approval_required without executing."
        ),
    )

    @mcp.tool()
    def list_hosts(limit: int = 100, offset: int = 0) -> dict[str, object]:
        """List target VPS hosts without exposing credential references or notes."""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        with get_sessionmaker()() as session:
            rows = (
                session.execute(
                    select(models.Host)
                    .order_by(models.Host.name.asc())
                    .limit(safe_limit)
                    .offset(safe_offset)
                )
                .scalars()
                .all()
            )
            return {"hosts": [_host_to_dict(row) for row in rows]}

    @mcp.tool()
    def list_recipes() -> dict[str, object]:
        """List built-in recipes with metadata only; raw YAML is omitted."""
        recipes: list[dict[str, object]] = []
        for recipe in list_builtin_recipes():
            safe = dict(recipe)
            safe.pop("yaml", None)
            recipes.append(safe)
        return {"recipes": recipes}

    @mcp.tool()
    def list_jobs(
        limit: int = 100,
        offset: int = 0,
        host_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        """List recent job summaries."""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        jobs = JobService(session_factory=get_sessionmaker()).list_jobs(
            limit=safe_limit,
            offset=safe_offset,
            host_id=host_id,
            status=status,
        )
        return {"jobs": [_job_to_dict(job) for job in jobs]}

    @mcp.tool()
    def run_recipe(
        host_id: str,
        recipe_name: str,
        vars: dict[str, object] | None = None,
        timeout_seconds: int = 600,
    ) -> dict[str, object]:
        """Run a low-risk built-in recipe, or return approval_required for high risk."""
        try:
            summary = get_builtin_recipe_summary(recipe_name)
            recipe_yaml = str(summary.get("yaml", ""))
            recipe = parse_recipe_text(recipe_yaml)
            environment = _get_host_environment(host_id)
        except (RecipeNotFoundError, RecipeSchemaError, ValueError) as exc:
            return {"error": _safe_text(exc)}

        decision = decision_for_recipe(recipe, environment=environment)
        risk = decision.risk_level
        if decision.blocked:
            return {
                "blocked": True,
                "executed": False,
                "reason": _safe_text(decision.reason),
                "recipe_name": recipe_name,
                "risk_level": risk.value,
            }
        if decision.approval_required or risk in _HIGH_RISK_LEVELS:
            return {
                "approval_required": True,
                "executed": False,
                "reason": f"Recipe {recipe_name} has risk_level={risk.value}",
                "recipe_name": recipe_name,
                "risk_level": risk.value,
            }

        try:
            job_id = _recipe_engine().run_recipe(
                recipe=recipe,
                host_id=host_id,
                actor_user_id=MCP_ACTOR_USER_ID,
                vars_values=vars or {},
                timeout_seconds=max(1, min(int(timeout_seconds), 86400)),
            )
        except RecipeSchemaError as exc:
            return {"error": _safe_text(exc)}
        with get_sessionmaker()() as session:
            job = session.execute(select(models.Job).where(models.Job.id == job_id)).scalar_one()
            return {
                "job_id": job.id,
                "status": job.status,
                "exit_code": job.exit_code,
                "approval_required": False,
                "executed": True,
                "recipe_name": recipe_name,
            }

    @mcp.tool()
    def get_job_status(
        job_id: str,
        include_logs: bool = True,
        log_limit: int = 200,
    ) -> dict[str, object]:
        """Return job status, steps, and redacted logs."""
        service = JobService(session_factory=get_sessionmaker())
        job = service.get(job_id)
        if job is None:
            return {"error": f"job not found: {job_id}"}
        steps = [_step_to_dict(step) for step in service.list_steps(job_id)]
        logs: list[dict[str, object]] = []
        if include_logs:
            logs = [
                _log_to_dict(log)
                for log in service.list_logs(job_id, limit=max(1, min(int(log_limit), 1000)))
            ]
        return {"job": _job_to_dict(job), "steps": steps, "logs": logs}

    return mcp


mcp = create_mcp_server()


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


__all__ = ["create_mcp_server", "main", "mcp"]
