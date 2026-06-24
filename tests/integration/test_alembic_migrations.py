"""Verify Alembic migrations apply cleanly to an empty SQLite database."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["VMAN_ENV"] = "development"
    # Force a sqlite URL independent of any local .env file.
    env["VMAN_DATABASE_URL"] = f"sqlite:///{db_path}"
    # Skip .env auto-load to avoid the placeholder-secret safety net.
    env["VMAN_DOTENV_PATH"] = "/dev/null"
    return subprocess.run(  # noqa: S603 (test invokes a fixed command)
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=60,
    )


def test_alembic_upgrade_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "vman.db"
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, (
        "alembic upgrade failed: stdout={result.stdout} stderr={result.stderr}"
    )
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    names = {row[0] for row in rows}
    assert {"alembic_version", "audit_events", "credentials", "encryption_keys"}.issubset(names)


def test_alembic_downgrade_then_upgrade_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "vman.db"
    upgrade = _run_alembic(db_path, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    downgrade = _run_alembic(db_path, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr
    upgrade_again = _run_alembic(db_path, "upgrade", "head")
    assert upgrade_again.returncode == 0, upgrade_again.stderr
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    names = {row[0] for row in rows}
    assert {"audit_events", "credentials", "encryption_keys"}.issubset(names)
