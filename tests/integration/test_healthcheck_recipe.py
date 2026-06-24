"""Integration tests for the built-in healthcheck recipe (Task 14).

These tests load the on-disk `healthcheck.yaml` recipe shipped with
VMAN and exercise it through the recipe engine using a fake SSH runner
so we can validate the recipe without touching a real target. They
cover the plan's acceptance criteria:

  - works on Debian/Ubuntu target
  - read-only
  - returns a resource summary (uptime, load, memory, disk, top CPU)

The recipe file itself is also parsed directly to confirm it stays
schema-valid as we evolve it.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

import vman.db.models  # noqa: F401  -- ensure models are registered
from vman.db import models
from vman.db.base import Base
from vman.db.session import get_sessionmaker, reset_engine
from vman.services.recipe_engine import (
    RecipeEngine,
    parse_recipe_text,
)
from vman.services.ssh_runner import CommandResult

HEALTHCHECK_RECIPE_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "vman"
    / "recipes"
    / "builtin"
    / "healthcheck.yaml"
)


@pytest.fixture()
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure VMAN to use a throwaway SQLite database for the test."""
    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    from vman.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    yield
    reset_engine()
    from vman.config import get_settings as _gs

    _gs.cache_clear()  # type: ignore[attr-defined]


def _seed_host(db_path: Path, *, name: str = "hc-host") -> str:
    """Insert a minimal Host row directly so the engine can look it up."""
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(
            models.Host.__table__.insert().values(
                id=host_id,
                name=name,
                hostname_or_ip="127.0.0.1",
                ssh_port=22,
                username="root",
                auth_method="key",
                created_at=now,
                updated_at=now,
            )
        )
    eng.dispose()
    return host_id


class _HealthcheckFakeRunner:
    """Fake SSH runner that emits plausible healthcheck output.

    We don't actually shell out — we just return realistic-looking
    text for each step so the recipe engine can record it as if a
    real Debian/Ubuntu target had been inspected.
    """

    def __init__(
        self,
        *,
        os_id: str = "ubuntu",
        os_version: str = "24.04",
        os_pretty: str = "Ubuntu 24.04 LTS",
        kernel: str = "Linux 6.8.0 x86_64",
        fail_step: str | None = None,
    ) -> None:
        self.os_id = os_id
        self.os_version = os_version
        self.os_pretty = os_pretty
        self.kernel = kernel
        self.fail_step = fail_step
        self.commands: list[str] = []

    def run(self, command: str, timeout: float = 30.0) -> CommandResult:
        self.commands.append(command)
        # Map step name heuristic from the command body to canned output.
        if "PRECHECK" in command or "os-release" in command or "/etc/os-release" in command:
            if self.fail_step == "detect-os":
                return CommandResult(
                    stdout="",
                    stderr="cannot read /etc/os-release",
                    exit_code=1,
                )
            stdout = (
                f"os_id={self.os_id}\n"
                f"os_version={self.os_version}\n"
                f"os_pretty={self.os_pretty}\n"
                f"{self.kernel}\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "uptime" in command or "/proc/uptime" in command:
            if self.fail_step == "uptime":
                return CommandResult(stdout="", stderr="boom", exit_code=2)
            stdout = (
                "uptime_seconds=424242\n"
                " 09:42:00 up 4 days, 21:37,  1 user,  load average: 0.05, 0.07, 0.04\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "free -m" in command:
            if self.fail_step == "memory":
                return CommandResult(stdout="", stderr="oops", exit_code=3)
            stdout = (
                "              total        used        free      shared  buff/cache   available\n"
                "Mem:           3926        1200         640          12        2086        2520\n"
                "Swap:          2047           10        2037\n"
                "---\n"
                "mem_total_kb=4019584\n"
                "mem_available_kb=2580480\n"
                "mem_free_kb=655360\n"
                "buffers_kb=212992\n"
                "cached_kb=1925120\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "df -P /" in command:
            if self.fail_step == "disk":
                return CommandResult(stdout="", stderr="disk error", exit_code=4)
            stdout = (
                "Filesystem     1024-blocks    Used Available Capacity Mounted on\n"
                "/dev/sda1        20511356 4832100 14567832      25% /\n"
                "---\n"
                "root_total_kb=20511356\n"
                "root_used_kb=4832100\n"
                "root_available_kb=14567832\n"
                "root_use_pct=25%\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "ps -eo" in command:
            if self.fail_step == "ps":
                return CommandResult(stdout="", stderr="ps broke", exit_code=5)
            stdout = (
                "    PID USER     %CPU %MEM COMMAND\n"
                "   1023 root      3.2  1.4 python3\n"
                "   2201 www-data  1.4  0.9 nginx\n"
                "   1834 root      0.7  0.5 sshd\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "ss -tulpn" in command or "netstat" in command:
            if self.fail_step == "ports":
                return CommandResult(stdout="", stderr="socket err", exit_code=6)
            stdout = (
                "Netid  State   Recv-Q  Send-Q   Local Address:Port   Peer Address:Port\n"
                "tcp    LISTEN  0       128      0.0.0.0:22           0.0.0.0:*\n"
                "tcp    LISTEN  0       4096     127.0.0.1:8000       0.0.0.0:*\n"
            )
            return CommandResult(stdout=stdout, stderr="", exit_code=0)
        if "healthcheck_complete" in command:
            return CommandResult(stdout="healthcheck_complete\n", stderr="", exit_code=0)
        # Default: succeed silently.
        return CommandResult(stdout="", stderr="", exit_code=0)


def test_healthcheck_yaml_is_valid_recipe() -> None:
    """The on-disk recipe must parse against the v1 schema."""
    text = HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8")
    recipe = parse_recipe_text(text)
    assert recipe["name"] == "healthcheck"
    assert recipe["risk_level"] == "low"
    assert recipe["supported_os"]["families"] == ["debian"]
    assert "ubuntu" in recipe["supported_os"]["names"]
    assert "debian" in recipe["supported_os"]["names"]
    # Read-only: every step must be non-mutating. We scan line-by-line
    # (after stripping comments) for the canonical dangerous verbs at
    # the start of a shell line. Substring matches in prose comments
    # like "form" would otherwise false-positive this check.
    forbidden_prefixes = (
        "rm ",
        "mv ",
        "cp ",
        "truncate ",
        "sed -i",
        "apt-get install",
        "apt install",
        "apt upgrade",
        "apt-get upgrade",
        "apt-get remove",
        "systemctl restart",
        "systemctl stop",
        "systemctl disable",
        "systemctl enable",
        "systemctl start",
        "systemctl mask",
        "shutdown ",
        "reboot",
        "poweroff",
        "halt",
        "mkfs",
        "dd if=",
    )

    def _stripped_command_lines(runs: list[str]) -> list[str]:
        out: list[str] = []
        for run in runs:
            for raw_line in run.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                out.append(line)
        return out

    for phase in ("preflight", "steps", "verify", "rollback"):
        for item in recipe.get(phase, []):
            lines = _stripped_command_lines([item["run"]])
            for line in lines:
                for bad in forbidden_prefixes:
                    assert not line.startswith(bad), (
                        f"healthcheck recipe must stay read-only; "
                        f"step {item['name']!r} in phase {phase!r} "
                        f"runs {bad!r}: {line!r}"
                    )


def test_healthcheck_yaml_has_resource_summary_steps() -> None:
    """The recipe must include the documented resource summary steps."""
    text = HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8")
    recipe = parse_recipe_text(text)
    step_names = {item["name"] for item in recipe.get("steps", [])}
    preflight_names = {item["name"] for item in recipe.get("preflight", [])}
    verify_names = {item["name"] for item in recipe.get("verify", [])}

    # OS detection happens in preflight so we can fail fast on the wrong OS.
    assert "detect-os" in preflight_names
    # The five required resource sections.
    assert "uptime-and-load" in step_names
    assert "memory" in step_names
    assert "disk-root" in step_names
    assert "top-cpu-processes" in step_names
    # Verify phase must complete the run cleanly.
    assert "summary-present" in verify_names

    # And the corresponding `run:` blocks must mention the right tools so
    # a careless edit (e.g. dropping `df -P /`) is caught.
    joined_runs = "\n".join(item["run"] for item in recipe["steps"])
    assert "/proc/uptime" in joined_runs
    assert "free -m" in joined_runs
    assert "df -P /" in joined_runs
    assert "ps -eo" in joined_runs
    # Load average should be reported via `uptime`.
    assert re.search(r"\buptime\b", joined_runs) is not None


def test_healthcheck_runs_end_to_end_and_records_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_env: None
) -> None:
    """End-to-end run via the recipe engine with a fake SSH runner."""
    db_path = tmp_path / "vman.db"
    host_id = _seed_host(db_path)
    recipe = parse_recipe_text(HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8"))
    runner = _HealthcheckFakeRunner()
    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: runner,
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )

    with get_sessionmaker()() as session:
        job = session.execute(select(models.Job).where(models.Job.id == job_id)).scalar_one()
        assert job.status == "success", f"job did not succeed: {job.error_summary}"
        assert job.exit_code == 0
        steps = (
            session.execute(
                select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            .scalars()
            .all()
        )

        # All steps must have succeeded. None should be skipped or failed.
        for step in steps:
            assert step.status == "success", f"step {step.name!r} status={step.status!r}"

        # Verify all expected phase:step pairs exist.
        names = {s.name for s in steps}
        for required in (
            "preflight:detect-os",
            "steps:uptime-and-load",
            "steps:memory",
            "steps:disk-root",
            "steps:top-cpu-processes",
            "steps:listening-ports",
            "verify:summary-present",
        ):
            assert required in names, f"missing step {required!r}; got {names}"

        # The captured logs must contain fragments of every resource
        # section so a real run would surface the data in the UI.
        log_rows = (
            session.execute(select(models.JobLog).where(models.JobLog.job_id == job_id))
            .scalars()
            .all()
        )
        log_text = "\n".join(row.line_redacted for row in log_rows)
        assert "mem_total_kb" in log_text
        assert "root_use_pct" in log_text
        assert "load average" in log_text
        assert "uptime_seconds" in log_text
        assert "python3" in log_text  # top CPU processes
        assert ":22" in log_text  # listening ports


def test_healthcheck_recipe_declares_ubuntu_debian_support() -> None:
    """Plan acceptance: works on Debian/Ubuntu."""
    recipe = parse_recipe_text(HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8"))
    families = recipe["supported_os"]["families"]
    names = recipe["supported_os"]["names"]
    assert "debian" in families
    assert "ubuntu" in names
    assert "debian" in names


def test_healthcheck_recipe_is_low_risk_and_needs_no_approval() -> None:
    """Plan acceptance: read-only => low risk => no approval required."""
    recipe = parse_recipe_text(HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8"))
    assert recipe["risk_level"] == "low"
    assert recipe["policy"].get("requires_approval") is False
    assert recipe["policy"].get("forbidden_on_environments") == []


def test_healthcheck_handles_step_failure_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_env: None
) -> None:
    """A failing healthcheck step must mark the job failed (and not crash)."""
    db_path = tmp_path / "vman.db"
    host_id = _seed_host(db_path)
    recipe = parse_recipe_text(HEALTHCHECK_RECIPE_PATH.read_text(encoding="utf-8"))
    runner = _HealthcheckFakeRunner(fail_step="disk")
    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: runner,
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )

    with get_sessionmaker()() as session:
        job = session.execute(select(models.Job).where(models.Job.id == job_id)).scalar_one()
        assert job.status == "failed"
        steps = (
            session.execute(
                select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            .scalars()
            .all()
        )
        statuses = [s.status for s in steps]
        assert "failed" in statuses
        # Once a step fails, downstream steps are skipped, not retried.
        assert "skipped" in statuses


def test_healthcheck_fake_runner_helper_is_internal() -> None:
    """Sanity check on the test fake: a no-op command still returns 0."""
    runner = _HealthcheckFakeRunner()
    result = runner.run("echo nothing")
    assert result.exit_code == 0


__all__: list[str] = []  # noqa: PYI019
