"""Shared FastAPI dependencies for the VMAN API."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from vman.config import Settings, get_settings
from vman.db import models
from vman.db.session import get_sessionmaker
from vman.security.auth import (
    hash_session_token,
)

SESSION_COOKIE_NAME: str = "vman_session"


def get_db() -> Session:  # type: ignore[misc]
    """FastAPI dependency that yields a SQLAlchemy session per request."""
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
    finally:
        session.close()


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbSession = Annotated[Session, Depends(get_db)]


def _client_ip(request: Request) -> str:
    """Return the best-effort client IP for rate limiting + audit.

    Honors ``X-Forwarded-For`` (first hop) when present; otherwise the
    raw socket address. Operators behind a reverse proxy must configure
    the proxy to set ``X-Forwarded-For`` accurately.
    """
    settings = get_settings()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and settings.trusted_proxy_hops > 0:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[0]
    if request.client is None:
        return "unknown"
    return request.client.host


def get_current_user(
    request: Request,
    db: DbSession,
    settings: SettingsDep,
) -> models.User:
    """Resolve the current user from the session cookie, or 401."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    token_hash = hash_session_token(token)
    now = dt.datetime.now(dt.timezone.utc)
    row = db.execute(
        select(models.UserSession)
        .where(models.UserSession.session_token_hash == token_hash)
        .where(models.UserSession.revoked_at.is_(None))
        .where(models.UserSession.expires_at > now)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session invalid or expired",
        )
    user = db.execute(select(models.User).where(models.User.id == row.user_id)).scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user disabled",
        )
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]


__all__ = [
    "CurrentUser",
    "DbSession",
    "SESSION_COOKIE_NAME",
    "SettingsDep",
    "get_client_ip_dep",
    "get_current_user",
    "get_db",
    "get_settings_dep",
    "client_ip",
]


# Provide both names so callers can import either.
get_client_ip_dep = _client_ip
client_ip = _client_ip
