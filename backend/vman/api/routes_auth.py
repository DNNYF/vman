"""Auth endpoints: setup, login, logout, /me, session list."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from vman.api.deps import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    DbSession,
    SettingsDep,
    client_ip,
)
from vman.db import models
from vman.db.session import get_sessionmaker
from vman.schemas.auth import LoginRequest, SetupRequest, UserOut
from vman.security.audit import AuditService
from vman.security.auth import (
    DEFAULT_SESSION_TTL,
    generate_session_token,
    get_rate_limiter,
    hash_password,
    hash_session_token,
    new_user_id,
    verify_password,
)
from vman.security.csrf import (
    clear_csrf_cookie,
    generate_csrf_token,
    hash_csrf_token,
    require_csrf,
    set_csrf_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_to_out(user: models.User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        totp_enabled=bool(user.totp_enabled),
    )


def _set_session_cookie(
    response: Response, token: str, ttl: dt.timedelta, settings: SettingsDep
) -> None:
    """Attach the session cookie with HttpOnly + SameSite=Lax."""
    secure = settings.is_production
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


# --------------------------------------------------------------------------- #
# POST /api/auth/setup  (first-admin)
# --------------------------------------------------------------------------- #


def _audit() -> AuditService:
    return AuditService(session_factory=get_sessionmaker())


@router.post(
    "/setup",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
)
def setup_first_admin(
    payload: SetupRequest,
    db: DbSession,
) -> UserOut:
    """Create the very first owner account.

    Only callable when the ``users`` table is empty. Once any user
    exists, this endpoint refuses with 409. Subsequent user management
    is an admin-only flow (out of scope for this task; arrives with
    RBAC in T7).
    """
    existing = db.execute(select(func.count(models.User.id))).scalar_one()
    if existing and existing > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="setup has already been completed",
        )
    user = models.User(
        id=new_user_id(),
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="owner",
        totp_enabled=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _audit().record(
        actor_user_id=user.id,
        actor_type="user",
        action="auth.setup",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username, "role": user.role},
    )
    return _user_to_out(user)


# --------------------------------------------------------------------------- #
# POST /api/auth/login
# --------------------------------------------------------------------------- #


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
) -> UserOut:
    """Authenticate by username + password, set the session cookie."""
    ip = client_ip(request)
    username_key = f"user:{payload.username.lower()}"
    ip_key = f"ip:{ip}"
    limiter = get_rate_limiter()
    if limiter.is_locked(ip_key) or limiter.is_locked(username_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed login attempts; try again later",
            headers={"Retry-After": "300"},
        )

    user = db.execute(
        select(models.User).where(models.User.username == payload.username)
    ).scalar_one_or_none()

    # Constant-ish time: still call verify_password even when the user
    # does not exist, so an attacker cannot distinguish by latency.
    if user is None or not user.password_hash:
        # Burn a verify call to keep timing similar.
        _decoy_hash = "$argon2id$v=19$m=65536,t=2,p=2$" + "x" * 22 + "$" + "y" * 43
        verify_password(payload.password, _decoy_hash)
        limiter.record_failure(ip_key)
        limiter.record_failure(username_key)
        _audit().record(
            actor_user_id=None,
            actor_type="user",
            action="auth.login.failure",
            resource_type="user",
            resource_id=user.id if user else "",
            ip_address=ip,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            metadata={"username": payload.username, "reason": "no_user_or_no_password"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if user.disabled_at is not None:
        limiter.record_failure(ip_key)
        limiter.record_failure(username_key)
        _audit().record(
            actor_user_id=user.id,
            actor_type="user",
            action="auth.login.failure",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            metadata={"username": payload.username, "reason": "disabled"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if not verify_password(payload.password, user.password_hash):
        limiter.record_failure(ip_key)
        limiter.record_failure(username_key)
        _audit().record(
            actor_user_id=user.id,
            actor_type="user",
            action="auth.login.failure",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            metadata={"username": payload.username, "reason": "bad_password"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    # Success: reset rate limiter, create session, set cookie.
    limiter.reset(ip_key)
    limiter.reset(username_key)
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    now = dt.datetime.now(dt.timezone.utc)
    session = models.UserSession(
        id=uuid.uuid4().hex,
        user_id=user.id,
        session_token_hash=hash_session_token(token),
        ip_address=ip,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        expires_at=now + DEFAULT_SESSION_TTL,
        created_at=now,
    )
    db.add(session)
    user.last_login_at = now
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, token, DEFAULT_SESSION_TTL, settings)
    set_csrf_cookie(response, csrf_token, settings)
    # Stash the CSRF hash on the session row so we can re-issue on rotate.
    # (The row itself does not need it for the double-submit check, but
    # storing it lets us revoke CSRF independently of session later.)
    session.csrf_token_hash = hash_csrf_token(csrf_token)
    db.commit()
    _audit().record(
        actor_user_id=user.id,
        actor_type="user",
        action="auth.login.success",
        resource_type="user",
        resource_id=user.id,
        ip_address=ip,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        metadata={"username": user.username, "session_id": session.id},
    )
    return _user_to_out(user)


# --------------------------------------------------------------------------- #
# POST /api/auth/logout
# --------------------------------------------------------------------------- #


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict[str, str]:
    """Revoke the current session and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        token_hash = hash_session_token(token)
        session = db.execute(
            select(models.UserSession).where(models.UserSession.session_token_hash == token_hash)
        ).scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="lax")
    clear_csrf_cookie(response)
    _audit().record(
        actor_user_id=user.id,
        actor_type="user",
        action="auth.logout",
        resource_type="user",
        resource_id=user.id,
    )
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# GET /api/auth/me
# --------------------------------------------------------------------------- #


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Return the currently-authenticated user."""
    return _user_to_out(user)


# --------------------------------------------------------------------------- #
# GET /api/auth/sessions  +  DELETE /api/auth/sessions/{id}
# --------------------------------------------------------------------------- #


@router.get("/sessions")
def list_sessions(user: CurrentUser, db: DbSession) -> list[dict[str, str | None]]:
    """List the current user's active sessions (for the dashboard)."""
    rows = (
        db.execute(
            select(models.UserSession)
            .where(models.UserSession.user_id == user.id)
            .order_by(models.UserSession.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[dict[str, str | None]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "expires_at": r.expires_at.isoformat() if r.expires_at else "",
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
            }
        )
    return out


@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
def revoke_session(
    session_id: str,
    user: CurrentUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict[str, str]:
    """Revoke one of the current user's sessions."""
    session = db.execute(
        select(models.UserSession).where(
            models.UserSession.id == session_id,
            models.UserSession.user_id == user.id,
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found",
        )
    if session.revoked_at is None:
        session.revoked_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    return {"status": "ok"}


__all__ = ["router"]
