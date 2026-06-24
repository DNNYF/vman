"""Tests for VMAN deployment helper scripts."""

from __future__ import annotations

import contextlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generate_master_key_outputs_valid_env_assignment() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO_ROOT / "scripts" / "generate-master-key.py")],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    match = re.search(r"^VMAN_MASTER_KEY=([A-Za-z0-9_-]{43}=)$", result.stdout, re.MULTILINE)
    assert match is not None
    assert "fingerprint" in result.stdout
    assert "do NOT commit" in result.stderr


import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="requires bash on POSIX platform")
def test_install_systemd_dry_run_writes_env_and_units(tmp_path: Path) -> None:

    systemd_dir = tmp_path / "systemd"
    config_dir = tmp_path / "etc-vman"
    varlib_dir = tmp_path / "lib-vman"
    data_dir = REPO_ROOT / "data"

    env = os.environ.copy()
    env.update(
        {
            "VMAN_SYSTEMD_DIR": str(systemd_dir),
            "VMAN_CONFIG_DIR": str(config_dir),
            "VMAN_VARLIB_DIR": str(varlib_dir),
            "VMAN_SKIP_SYSTEMCTL": "1",
        }
    )

    try:
        subprocess.run(  # noqa: S603
            ["/usr/bin/bash", str(REPO_ROOT / "scripts" / "install-systemd.sh")],
            cwd=REPO_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        # The installer creates the runtime data directory when run from tests.
        # Remove it if it is still empty so the repository stays clean.
        with contextlib.suppress(OSError):
            data_dir.rmdir()

    env_file = config_dir / "vman.env"
    api_unit = systemd_dir / "vman-api.service"
    worker_unit = systemd_dir / "vman-worker.service"

    assert env_file.exists()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    env_text = env_file.read_text(encoding="utf-8")
    assert "VMAN_ENV=production" in env_text
    assert "VMAN_DATABASE_URL=sqlite:////var/lib/vman/vman.db" in env_text
    assert (
        "VMAN_MASTER_KEY=CHANGEME-GENERATE-WITH-python-scripts-generate-master-key-py"
        in env_text
    )

    api_text = api_unit.read_text(encoding="utf-8")
    worker_text = worker_unit.read_text(encoding="utf-8")
    assert "Description=VMAN API service" in api_text
    assert f"EnvironmentFile={env_file}" in api_text
    assert "ExecStart=" in api_text
    assert "vman-api" in api_text or "uvicorn vman.main:app" in api_text

    assert "Description=VMAN worker service" in worker_text
    assert f"EnvironmentFile={env_file}" in worker_text
    assert "ExecStart=" in worker_text
    assert "vman-worker" in worker_text or "-m vman.worker" in worker_text


def test_deployment_docs_include_systemd_and_health_instructions() -> None:
    docs = (REPO_ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    assert "scripts/install-systemd.sh" in docs
    assert "scripts/generate-master-key.py" in docs
    assert "systemctl status vman-api" in docs
    assert "systemctl status vman-worker" in docs
    assert "curl -fsS http://127.0.0.1:8765/api/health" in docs
