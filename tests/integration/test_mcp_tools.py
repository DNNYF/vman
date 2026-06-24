"""Integration tests for the VMAN MCP tools (Task 20)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine

from vman.config import get_settings
from vman.db import models
from vman.db.base import Base
from vman.db.session import reset_engine
from vman.services.recipe_engine import clear_builtin_recipe_cache


def _structured_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return result[1]
    if isinstance(result, dict):
        return result
    raise TypeError(f"unexpected MCP tool result: {type(result)!r}")


@pytest.fixture()
def mcp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    low_recipe = """
schema_version: 1
name: safe-echo
version: 0.1.0
description: Safe echo test recipe
risk_level: low
steps:
  - name: echo
    run: echo hello-mcp
""".strip()
    high_recipe = """
schema_version: 1
name: dangerous-upgrade
version: 0.1.0
description: Requires approval before changing a host
risk_level: high
steps:
  - name: upgrade
    run: sudo apt-get dist-upgrade -y
""".strip()
    (recipes_dir / "safe-echo.yaml").write_text(low_recipe, encoding="utf-8")
    (recipes_dir / "dangerous-upgrade.yaml").write_text(high_recipe, encoding="utf-8")

    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("VMAN_BUILTIN_RECIPES_DIR", str(recipes_dir))
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    clear_builtin_recipe_cache()

    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name="test-host",
                hostname_or_ip="127.0.0.1",
                ssh_port=22,
                username="root",
                auth_method="key",
                credential_id="cred-secret-ref",
                sudo_mode="root",
                host_key_fingerprint="SHA256:not-a-secret",
                host_key_algorithm="ed25519",
                notes="token=super-secret-notes",
                environment="experiment",
                tags=["mcp"],
                created_at=now,
                updated_at=now,
            )
        )
        conn.execute(
            models.Job.__table__.insert().values(
                id="job-existing",
                host_id=host_id,
                recipe_name="safe-echo",
                command_summary="recipe: safe-echo@0.1.0",
                status="success",
                risk_level="low",
                approval_status="not_required",
                timeout_seconds=60,
                exit_code=0,
                created_at=now,
                updated_at=now,
            )
        )
    eng.dispose()
    yield {"host_id": host_id, "db_path": db_path}
    clear_builtin_recipe_cache()
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mcp_lists_safe_host_recipe_and_job_summaries(mcp_db) -> None:
    from vman.mcp.server import create_mcp_server

    server = create_mcp_server()
    tool_names = {tool.name for tool in await server.list_tools()}
    assert {"list_hosts", "list_recipes", "list_jobs"}.issubset(tool_names)

    hosts = _structured_tool_result(await server.call_tool("list_hosts", {}))
    assert hosts["hosts"][0]["id"] == mcp_db["host_id"]
    assert hosts["hosts"][0]["name"] == "test-host"
    assert "credential_id" not in hosts["hosts"][0]
    assert "super-secret-notes" not in repr(hosts)

    recipes = _structured_tool_result(await server.call_tool("list_recipes", {}))
    assert {recipe["name"] for recipe in recipes["recipes"]} == {
        "dangerous-upgrade",
        "safe-echo",
    }
    assert all("yaml" not in recipe for recipe in recipes["recipes"])

    jobs = _structured_tool_result(await server.call_tool("list_jobs", {}))
    assert jobs["jobs"][0]["id"] == "job-existing"
    assert jobs["jobs"][0]["recipe_name"] == "safe-echo"


@pytest.mark.asyncio
async def test_mcp_runs_low_risk_recipe_and_reports_status(mcp_db, monkeypatch) -> None:
    from vman.mcp import server as server_module
    from vman.mcp.server import create_mcp_server
    from vman.services.ssh_runner import CommandResult

    class FakeRunner:
        def __init__(self, host) -> None:
            self.host = host

        def run(self, command: str, *, timeout: float = 300.0) -> CommandResult:
            assert command == "echo hello-mcp"
            return CommandResult(stdout="hello-mcp\n", stderr="", exit_code=0)

    monkeypatch.setattr(server_module, "_mcp_runner_factory", lambda host: FakeRunner(host))

    server = create_mcp_server()
    run_result = _structured_tool_result(
        await server.call_tool(
            "run_recipe",
            {"host_id": mcp_db["host_id"], "recipe_name": "safe-echo"},
        )
    )
    assert run_result["status"] == "success"
    assert run_result["approval_required"] is False
    assert run_result["job_id"]

    status = _structured_tool_result(
        await server.call_tool("get_job_status", {"job_id": run_result["job_id"]})
    )
    assert status["job"]["status"] == "success"
    assert status["job"]["exit_code"] == 0
    assert status["logs"][-1]["line"] == "hello-mcp"
    assert "super-secret" not in repr(status)


@pytest.mark.asyncio
async def test_mcp_high_risk_recipe_requires_approval_without_executing(
    mcp_db, monkeypatch
) -> None:
    from vman.mcp import server as server_module
    from vman.mcp.server import create_mcp_server

    called = False

    def fail_if_called(host):
        nonlocal called
        called = True
        raise AssertionError("high-risk recipe must not execute")

    monkeypatch.setattr(server_module, "_mcp_runner_factory", fail_if_called)

    server = create_mcp_server()
    result = _structured_tool_result(
        await server.call_tool(
            "run_recipe",
            {"host_id": mcp_db["host_id"], "recipe_name": "dangerous-upgrade"},
        )
    )
    assert result == {
        "approval_required": True,
        "executed": False,
        "reason": "Recipe dangerous-upgrade has risk_level=high",
        "recipe_name": "dangerous-upgrade",
        "risk_level": "high",
    }
    assert called is False
