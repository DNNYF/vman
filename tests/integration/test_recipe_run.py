"""Integration tests for recipe execution (Milestone 4 / Task 13)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vman.config import get_settings
from vman.db import models
from vman.db.session import get_sessionmaker, reset_engine
from vman.main import create_app
from vman.services.recipe_engine import (
    RecipeEngine,
    parse_recipe_text,
)
from vman.services.ssh_runner import CommandResult


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "vman.db"
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    yield TestClient(create_app())
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


def _seed_host(db_path: Path, *, name: str = "host-x") -> str:
    """Create a host row and return its id."""
    import datetime as dt

    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(eng)
    host_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
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


def test_recipe_engine_runs_in_process(tmp_path, monkeypatch) -> None:
    """A trivial recipe with a single echo step should succeed."""
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{tmp_path / 'vman.db'}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path / 'vman.db'}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    host_id = _seed_host(tmp_path / "vman.db")

    recipe_yaml = """
schema_version: 1
name: simple-echo
version: 0.1.0
risk_level: low
steps:
  - name: say-hi
    run: echo hello-recipe
"""
    recipe = parse_recipe_text(recipe_yaml)
    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: _FakeRunner(["hello-recipe\n"]),
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )
    assert job_id
    # Job should be in success state (we ran synchronously).
    with get_sessionmaker()() as s:
        from sqlalchemy import select as _select

        job = s.execute(_select(models.Job).where(models.Job.id == job_id)).scalar_one()
        assert job.status == "success"
        assert job.exit_code == 0
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_recipe_engine_persists_step_logs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{tmp_path / 'vman.db'}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path / 'vman.db'}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    host_id = _seed_host(tmp_path / "vman.db")

    recipe_yaml = """
schema_version: 1
name: two-step
version: 0.1.0
risk_level: low
steps:
  - name: step-one
    run: echo one
  - name: step-two
    run: echo two
"""
    recipe = parse_recipe_text(recipe_yaml)
    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: _FakeRunner(["one\n", "two\n"]),
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )
    with get_sessionmaker()() as s:
        from sqlalchemy import select as _select

        steps = (
            s.execute(
                _select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            .scalars()
            .all()
        )
        assert len(steps) == 2
        assert steps[0].name == "steps:step-one"
        assert steps[0].status == "success"
        assert steps[1].name == "steps:step-two"
        assert steps[1].status == "success"
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_recipe_engine_records_failure_on_nonzero_exit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{tmp_path / 'vman.db'}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path / 'vman.db'}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    host_id = _seed_host(tmp_path / "vman.db")

    recipe_yaml = """
schema_version: 1
name: fails
version: 0.1.0
risk_level: low
steps:
  - name: step-one
    run: echo a
  - name: step-two
    run: this-command-does-not-exist
  - name: step-three
    run: echo should-not-run
"""
    recipe = parse_recipe_text(recipe_yaml)
    from vman.services.ssh_runner import CommandResult

    def _behaviour(cmd: str) -> CommandResult:
        if "this-command-does-not-exist" in cmd:
            return CommandResult(stdout="", stderr="not found", exit_code=127)
        return CommandResult(stdout="ok", stderr="", exit_code=0)

    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: _FakeRunner(_behaviour=_behaviour),
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )
    with get_sessionmaker()() as s:
        from sqlalchemy import select as _select

        job = s.execute(_select(models.Job).where(models.Job.id == job_id)).scalar_one()
        assert job.status == "failed"
        steps = (
            s.execute(
                _select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            .scalars()
            .all()
        )
        assert steps[0].status == "success"
        assert steps[1].status == "failed"
        # step-three should be skipped.
        assert steps[2].status == "skipped"
        # step-three name has the steps: prefix.
        assert steps[2].name == "steps:step-three"
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_recipe_engine_runs_verify_and_rollback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VMAN_ENV", "development")
    monkeypatch.setenv("VMAN_DATABASE_URL", f"sqlite:///{tmp_path / 'vman.db'}")
    monkeypatch.setenv("VMAN_DOTENV_PATH", "/dev/null")
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from sqlalchemy import create_engine

    import vman.db.models  # noqa: F401
    from vman.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path / 'vman.db'}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    host_id = _seed_host(tmp_path / "vman.db")

    recipe_yaml = """
schema_version: 1
name: with-verify
version: 0.1.0
risk_level: low
steps:
  - name: install
    run: echo install
verify:
  - name: post-check
    run: echo verified
rollback:
  - name: undo
    run: echo undone
"""
    recipe = parse_recipe_text(recipe_yaml)
    engine = RecipeEngine(
        session_factory=get_sessionmaker(),
        ssh_runner_factory=lambda h: _FakeRunner(["install\n", "verified\n", "undone\n"]),
    )
    job_id = engine.run_recipe(
        recipe=recipe,
        host_id=host_id,
        actor_user_id=None,
        vars_values={},
    )
    with get_sessionmaker()() as s:
        from sqlalchemy import select as _select

        steps = (
            s.execute(
                _select(models.JobStep)
                .where(models.JobStep.job_id == job_id)
                .order_by(models.JobStep.step_index.asc())
            )
            .scalars()
            .all()
        )
        # 1 step + 1 verify step = 2 successful steps. rollback only
        # runs on failure. Step names are prefixed with the phase.
        names = [s.name for s in steps]
        assert "steps:install" in names
        assert "verify:post-check" in names
        assert "rollback:undo" not in names  # no failure -> no rollback
    reset_engine()
    get_settings.cache_clear()  # type: ignore[attr-defined]


class _FakeRunner:
    def __init__(
        self,
        stdout_lines: list[str] | None = None,
        _behaviour: Callable[[str], CommandResult] | None = None,
    ) -> None:
        self.stdout_lines = stdout_lines or []
        self._behaviour = _behaviour

    def run(self, command: str, timeout: float = 30.0) -> CommandResult:
        from vman.services.ssh_runner import CommandResult

        if self._behaviour is not None:
            return self._behaviour(command)
        return CommandResult(
            stdout=(self.stdout_lines.pop(0) if self.stdout_lines else ""),
            stderr="",
            exit_code=0,
        )
