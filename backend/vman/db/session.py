"""Database engine and session factory for VMAN.

The engine is built lazily from ``Settings.database_url`` so tests can
inject a different URL (in-memory SQLite) by calling ``reset_engine``
before any model code runs. Production code should rely on the global
``get_engine`` / ``get_sessionmaker`` helpers.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vman.config import get_settings
from vman.db.base import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine(url: str) -> Engine:
    """Build an Engine with sensible defaults for both SQLite and Postgres."""
    if url.startswith("sqlite"):
        # SQLite needs check_same_thread=False for FastAPI's threadpool.
        return create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine() -> Engine:
    """Return the process-wide Engine, creating it on first use."""
    global _engine
    if _engine is None:
        url = os.environ.get("VMAN_DATABASE_URL_OVERRIDE") or get_settings().database_url
        _engine = _build_engine(url)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide ``sessionmaker`` bound to the engine."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


class SessionFactory:
    """Thin convenience wrapper around ``sessionmaker`` for FastAPI deps.

    Two equivalent ways to use it:

    - As a generator dependency: ``def endpoint(s = Depends(SessionFactory())):``
      -- yields a fresh Session per request, closes on exit.
    - As a context manager: ``with SessionFactory() as s:`` -- single session.
    """

    _ctx_session: Session | None

    def __init__(
        self,
        engine: Engine | None = None,
        sessionmaker_: sessionmaker[Session] | None = None,
    ) -> None:
        self._engine = engine
        self._sessionmaker = sessionmaker_
        self._ctx_session = None

    @contextmanager
    def __call__(self) -> Iterator[Session]:
        sm = self._sessionmaker or get_sessionmaker()
        session = sm()
        try:
            yield session
        finally:
            session.close()

    # Backwards-compat: keep generator-only path available for FastAPI deps.
    def iter(self) -> Iterator[Session]:
        sm = self._sessionmaker or get_sessionmaker()
        session = sm()
        try:
            yield session
        finally:
            session.close()

    def __enter__(self) -> Session:
        sm = self._sessionmaker or get_sessionmaker()
        self._ctx_session = sm()
        return self._ctx_session

    def __exit__(self, exc_type, exc, tb) -> None:
        session = getattr(self, "_ctx_session", None)
        if session is not None:
            try:
                if exc_type is not None:
                    session.rollback()
            finally:
                session.close()


def reset_engine() -> None:
    """Drop cached engine/sessionmaker (tests only)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for ad-hoc scripts (CLI, Alembic helpers, tests)."""
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "Base",
    "Engine",
    "Session",
    "SessionFactory",
    "get_engine",
    "get_sessionmaker",
    "reset_engine",
    "session_scope",
]
