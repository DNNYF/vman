"""Auth primitives: Argon2id password hashing + session token handling.

Security notes
--------------
- Passwords are hashed with Argon2id (RFC 9106 recommended). The hash
  encodes the salt, memory cost, time cost, and parallelism, so we
  do not need to track those parameters separately.
- Session tokens are 32 random bytes (256 bits), URL-safe base64
  encoded for the cookie. The DB stores only the SHA-256 of the token,
  never the token itself -- a database compromise does NOT yield
  usable cookies.
- Login rate limiting is done in-process with a tiny fixed-window
  counter. For a single-control-VPS MVP this is sufficient. A
  distributed Redis-backed limiter can replace it later without
  changing the auth API.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import threading
import uuid
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Minimum length for any user-supplied password. Long passphrases are
# encouraged; this is a sane floor that blocks obvious junk.
MIN_PASSWORD_LENGTH: Final[int] = 12

# Default session lifetime. Operators can override via Settings later.
DEFAULT_SESSION_TTL: Final[dt.timedelta] = dt.timedelta(hours=12)

# Rate limit: max failed login attempts per IP per window.
LOGIN_RATE_LIMIT_MAX_FAILS: Final[int] = 5
LOGIN_RATE_LIMIT_WINDOW: Final[dt.timedelta] = dt.timedelta(minutes=5)
LOGIN_RATE_LIMIT_USERNAME_MAX_FAILS: Final[int] = 10


# --------------------------------------------------------------------------- #
# Password hashing (Argon2id)
# --------------------------------------------------------------------------- #


def _hasher() -> PasswordHasher:
    """Return a PasswordHasher with safe defaults (Argon2id, ~64 MiB)."""
    # The defaults are already Argon2id; we set explicit costs so the
    # hash parameters are predictable and reviewed.
    return PasswordHasher(
        time_cost=2,
        memory_cost=64 * 1024,  # 64 MiB
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )


def hash_password(plaintext: str) -> str:
    """Hash ``plaintext`` with Argon2id. Returns the encoded hash string."""
    if not plaintext:
        raise ValueError("password must be a non-empty string")
    if len(plaintext) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher().hash(plaintext)


def verify_password(plaintext: str, encoded_hash: str) -> bool:
    """Return True iff ``plaintext`` matches the Argon2id ``encoded_hash``.

    Raises ``ValueError`` on malformed hashes -- callers should treat
    that as a verification failure (do not propagate to the user).
    """
    if not plaintext or not encoded_hash:
        return False
    try:
        return _hasher().verify(encoded_hash, plaintext)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed hash: treat as a failure rather than a 500.
        return False


def needs_rehash(encoded_hash: str) -> bool:
    """Return True if the stored hash should be re-derived (e.g. costs bumped)."""
    try:
        return _hasher().check_needs_rehash(encoded_hash)
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Session tokens
# --------------------------------------------------------------------------- #


def generate_session_token() -> str:
    """Return a fresh 256-bit URL-safe session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Return the SHA-256 hex digest of a session token (DB representation)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Login rate limiter
# --------------------------------------------------------------------------- #


class _RateLimitBucket:
    __slots__ = ("fails", "window_start")

    def __init__(self) -> None:
        self.fails: int = 0
        self.window_start: dt.datetime = dt.datetime.now(dt.timezone.utc)


class LoginRateLimiter:
    """Tiny in-process fixed-window login rate limiter.

    Tracks the number of failed login attempts per key over a rolling
    window. Routes use both IP and username-derived keys so an attacker
    cannot bypass the limiter by rotating one dimension only. This is
    sufficient for MVP -- a single central VPS, single uvicorn worker.
    """

    def __init__(
        self,
        *,
        max_fails: int = LOGIN_RATE_LIMIT_MAX_FAILS,
        window: dt.timedelta = LOGIN_RATE_LIMIT_WINDOW,
    ) -> None:
        self._max_fails = max_fails
        self._window = window
        self._buckets: dict[str, _RateLimitBucket] = {}
        self._lock = threading.Lock()

    def _bucket(self, key: str) -> _RateLimitBucket:
        now = dt.datetime.now(dt.timezone.utc)
        bucket = self._buckets.get(key)
        if bucket is None or (now - bucket.window_start) >= self._window:
            bucket = _RateLimitBucket()
            self._buckets[key] = bucket
        return bucket

    def is_locked(self, key: str) -> bool:
        with self._lock:
            return self._bucket(key).fails >= self._max_fails

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._bucket(key).fails += 1

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """Clear all buckets; used by tests and admin maintenance hooks."""
        with self._lock:
            self._buckets.clear()


# Module-level singleton used by the auth API.
_rate_limiter = LoginRateLimiter()


def get_rate_limiter() -> LoginRateLimiter:
    """Return the process-wide rate limiter (for tests + dependency injection)."""
    return _rate_limiter


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def new_user_id() -> str:
    """Generate a fresh UUID4 hex string (no dashes) for primary keys."""
    return uuid.uuid4().hex


__all__ = [
    "DEFAULT_SESSION_TTL",
    "LOGIN_RATE_LIMIT_MAX_FAILS",
    "LOGIN_RATE_LIMIT_USERNAME_MAX_FAILS",
    "LOGIN_RATE_LIMIT_WINDOW",
    "LoginRateLimiter",
    "MIN_PASSWORD_LENGTH",
    "generate_session_token",
    "get_rate_limiter",
    "hash_password",
    "hash_session_token",
    "needs_rehash",
    "new_user_id",
    "verify_password",
]
