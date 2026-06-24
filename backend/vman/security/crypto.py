"""AES-256-GCM primitives for VMAN credential encryption.

Design notes
------------
- Algorithm: AES-256-GCM (96-bit random nonce, 128-bit auth tag).
- Output layout: ``VERSION(1) || NONCE(12) || CIPHERTEXT(N) || TAG(16)``.
  The version byte at position 0 lets us introduce v2 (e.g.
  XChaCha20-Poly1305) without breaking already-stored rows; old rows
  are still decryptable because we read the version first.
- AAD (associated authenticated data) binds the ciphertext to the
  credential identity (``credential_id`` + ``kind``). A ciphertext
  stored for credential A MUST NOT decrypt under credential B's AAD.
  This blocks cross-credential replay attacks.
- The master key MUST come from the operator-supplied environment
  variable, never from disk. ``generate_master_key`` exists for setup
  scripts and tests; production code paths must NOT call it.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Output layout constants. Bumping VERSION allows format migration.
_VERSION_V1: Final[bytes] = b"\x01"
_NONCE_BYTES: Final[int] = 12  # GCM-recommended nonce size
_TAG_BYTES: Final[int] = 16  # GCM tag is appended by cryptography


class CryptoError(Exception):
    """Raised on any decryption failure (wrong key, wrong AAD, tampered data)."""


def generate_master_key() -> bytes:
    """Return 32 fresh random bytes for use as an AES-256 master key.

    Uses ``secrets.token_bytes`` (os.urandom-backed) so the result is
    suitable for cryptography. NEVER log this value.
    """
    return secrets.token_bytes(32)


def key_fingerprint(key: bytes) -> str:
    """Return a short, NON-SECRET display fingerprint for a key.

    Useful for operators comparing keys out-of-band. We deliberately
    return the FIRST 16 hex chars of SHA-256(key) -- long enough to be
    unique in practice, short enough to be human-readable.
    """
    digest = hashlib.sha256(key).hexdigest()
    return digest[:16]


def _split(payload: bytes) -> tuple[bytes, bytes]:
    """Split ``VERSION || NONCE || CIPHERTEXT+TAG`` into (nonce, ct+tag).

    Validates the layout and version byte.
    """
    if len(payload) < 1 + _NONCE_BYTES + _TAG_BYTES:
        raise CryptoError("ciphertext is too short to be valid")
    version = payload[:1]
    if version != _VERSION_V1:
        raise CryptoError(f"unsupported ciphertext version: {version!r}")
    nonce = payload[1 : 1 + _NONCE_BYTES]
    ct_and_tag = payload[1 + _NONCE_BYTES :]
    if len(ct_and_tag) < _TAG_BYTES:
        raise CryptoError("ciphertext is too short to be valid")
    return nonce, ct_and_tag


def encrypt_bytes(key: bytes, plaintext: bytes, *, aad: bytes = b"") -> bytes:
    """Encrypt ``plaintext`` under ``key`` with the given AAD.

    Returns ``VERSION || NONCE || CIPHERTEXT || TAG``. The nonce is
    cryptographically random per call.
    """
    if len(key) != 32:
        raise CryptoError("master key must be exactly 32 bytes (AES-256)")
    if len(aad) >= 64 * 1024:
        # cryptography's GCM raises ValueError for oversized AAD; we catch
        # this in the test, but flagging it here makes the contract explicit.
        raise CryptoError("AAD must be smaller than 64 KiB")
    nonce = secrets.token_bytes(_NONCE_BYTES)
    cipher = AESGCM(key)
    ct_and_tag = cipher.encrypt(nonce, plaintext, aad)
    return _VERSION_V1 + nonce + ct_and_tag


def decrypt_bytes(key: bytes, payload: bytes, *, aad: bytes = b"") -> bytes:
    """Decrypt ``payload`` (as produced by :func:`encrypt_bytes`) under ``key``.

    Raises :class:`CryptoError` on any failure (wrong key, wrong AAD,
    tampered ciphertext, malformed layout). The underlying
    ``cryptography`` library raises ``InvalidTag`` on auth failure; we
    wrap that into a single :class:`CryptoError` so callers only handle
    one exception type.
    """
    if len(key) != 32:
        raise CryptoError("master key must be exactly 32 bytes (AES-256)")
    try:
        nonce, ct_and_tag = _split(payload)
    except CryptoError:
        raise
    cipher = AESGCM(key)
    try:
        return cipher.decrypt(nonce, ct_and_tag, aad)
    except InvalidTag as exc:
        raise CryptoError(
            "decryption failed: invalid tag (wrong key, wrong AAD, or tampered ciphertext)"
        ) from exc


def encode_master_key_for_env(key: bytes) -> str:
    """Encode a raw key as URL-safe base64 for storing in an env file.

    This is the only safe text representation: it is reversible, has
    no special characters that shell-quoting would mangle, and the
    resulting string is visibly "machine data" to anyone reading .env.
    """
    import base64

    return base64.urlsafe_b64encode(key).decode("ascii")


def decode_master_key_from_env(value: str) -> bytes:
    """Decode a key previously produced by :func:`encode_master_key_for_env`."""
    import base64

    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise CryptoError("master key is not valid url-safe base64") from exc
    if len(raw) != 32:
        raise CryptoError(f"master key decoded to {len(raw)} bytes; expected exactly 32")
    return raw


__all__ = [
    "CryptoError",
    "decrypt_bytes",
    "encode_master_key_for_env",
    "decode_master_key_from_env",
    "encrypt_bytes",
    "generate_master_key",
    "key_fingerprint",
]
