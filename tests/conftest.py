"""Shared pytest fixtures for VMAN tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter() -> None:
    """Keep the in-process auth limiter isolated per test case."""
    from vman.security.auth import get_rate_limiter

    get_rate_limiter().reset_all()
