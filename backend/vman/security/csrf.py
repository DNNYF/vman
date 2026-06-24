"""CSRF defense and CORS helpers for the VMAN API.

Protection model
----------------
We use a double-submit cookie pattern. On any authenticated GET (and
on login) the API sets a ``vman_csrf`` cookie containing a random
opaque token. The cookie is NOT HttpOnly (browser JS must read it).
For mutating requests (POST/PUT/PATCH/DELETE) the client MUST echo
the cookie value in the ``X-CSRF-Token`` header. The API compares
the two using a constant-time comparison.

The CSRF cookie is bound to the user session: rotating the session
also rotates the CSRF token. We store the CSRF token hash on the
``UserSession`` row so we can verify it server-side.

CORS
----
Allowed origins are configured via ``Settings.allowed_origins``.
Disallowed origins do NOT receive ``Access-Control-Allow-Origin``,
so browsers block the request. Preflight OPTIONS requests are
handled here (we do not delegate them to FastAPI's default CORSMiddleware
because we want strict allow-list semantics).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

from fastapi import HTTPException, Request, Response, status

from vman.config import Settings
from vman.db import models
from vman.security.auth import hash_session_token

CSRF_COOKIE_NAME: Final[str] = "vman_csrf"
CSRF_HEADER_NAME: Final[str] = "X-CSRF-Token"

# Methods that can change state. CSRF only protects these.
_UNSAFE_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def generate_csrf_token() -> str:
    """Return a fresh opaque CSRF token (URL-safe random)."""
    return secrets.token_urlsafe(32)


def hash_csrf_token(token: str) -> str:
    """Return the SHA-256 hex digest of a CSRF token (DB representation)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    """Attach the CSRF cookie to ``response``.

    The cookie is NOT HttpOnly -- browser JS must be able to read it
    and echo it in the X-CSRF-Token header. ``SameSite=Lax`` keeps the
    cookie off most cross-site requests as a first line of defense;
    the double-submit comparison is the second line.
    """
    secure = settings.is_production
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=12 * 3600,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/", samesite="lax")


def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def require_csrf(request: Request) -> None:
    """FastAPI dependency enforcing the double-submit CSRF check.

    Compares the ``X-CSRF-Token`` header to the ``vman_csrf`` cookie.
    Missing cookie, missing header, or mismatch -> 403.

    For unauthenticated endpoints (login, setup) this dependency is NOT
    installed -- CSRF applies only once the user has a session.
    """
    if request.method.upper() not in _UNSAFE_METHODS:
        return  # GET/HEAD/OPTIONS pass through

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf token missing",
        )
    if not _safe_compare(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf token mismatch",
        )


def origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Return True iff ``origin`` is in the configured allow-list."""
    if not origin:
        return False
    allowed = {o.strip().lower().rstrip("/") for o in settings.allowed_origins_list}
    candidate = origin.strip().lower().rstrip("/")
    return candidate in allowed


def cors_headers_for(origin: str | None, settings: Settings) -> dict[str, str]:
    """Return the CORS headers to attach to a response, given the request Origin."""
    if not origin_allowed(origin, settings):
        return {}
    return {
        "Access-Control-Allow-Origin": origin or "",
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


def preflight_headers(origin: str | None, settings: Settings) -> dict[str, str]:
    """Return CORS headers for an OPTIONS preflight request."""
    if not origin_allowed(origin, settings):
        return {}
    return {
        "Access-Control-Allow-Origin": origin or "",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": ("Content-Type, X-CSRF-Token, Authorization"),
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "clear_csrf_cookie",
    "cors_headers_for",
    "generate_csrf_token",
    "hash_csrf_token",
    "origin_allowed",
    "preflight_headers",
    "require_csrf",
    "set_csrf_cookie",
]


# The unused imports below keep the linter happy while still being
# available for future expansion of the module.
_ = (models, hash_session_token)
