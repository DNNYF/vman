"""SSH host key fingerprint handling (Milestone 2 / Task 9).

The host key fingerprint is what binds a Host record to a specific
SSH server. On the first connection we record the fingerprint ONLY
after the operator explicitly trusts it. On every subsequent
connection we verify the fingerprint matches; a mismatch blocks the
command and surfaces a "fingerprint mismatch" error to the user.

We use the standard SHA-256 over the host key's public-key bytes,
formatted as ``SHA256:base64`` to match what OpenSSH prints as
``ssh-keygen -lf``.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

# Accepted algorithms for stored host keys. We are deliberately narrow
# here: newer is safer, and the plan calls for strict host key checking.
SUPPORTED_ALGORITHMS: frozenset[str] = frozenset(
    {
        "ssh-ed25519",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "rsa-sha2-256",
        "rsa-sha2-512",
        "ssh-rsa",
        "ssh-dss",
    }
)

# Regex for the SHA-256 OpenSSH fingerprint format.
_FP_RE = re.compile(r"^SHA256:([A-Za-z0-9+/=]+)$")


@dataclass(frozen=True)
class HostKeyFingerprint:
    """Parsed host key fingerprint."""

    algorithm: str
    fingerprint: str  # "SHA256:<base64>" format

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.fingerprint}"


def parse_fingerprint(algorithm: str, raw: str) -> HostKeyFingerprint:
    """Parse a host key fingerprint string.

    Accepts:
    - The OpenSSH "SHA256:base64" form (the most common).
    - The colon-separated MD5 form (legacy, e.g. "aa:bb:cc:...").

    Returns a canonical ``HostKeyFingerprint`` with the
    SHA-256 form preferred when the input is MD5.
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"unsupported host key algorithm: {algorithm!r}; "
            f"must be one of {sorted(SUPPORTED_ALGORITHMS)}"
        )
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("fingerprint must not be empty")
    if raw.startswith("SHA256:"):
        body = raw.split(":", 1)[1]
        # OpenSSH strips trailing "=" padding from the displayed
        # fingerprint; tolerate that. We re-pad and round-trip-decode
        # to make sure the body is real base64, not random characters.
        padded = body + "=" * (-len(body) % 4)
        try:
            base64.b64decode(padded, validate=True)
        except Exception as exc:
            raise ValueError(f"fingerprint is not valid base64: {exc}") from exc
        return HostKeyFingerprint(algorithm=algorithm, fingerprint=raw)
    # MD5 form
    if re.fullmatch(r"([0-9a-fA-F]{2}:){15}[0-9a-fA-F]{2}", raw):
        return HostKeyFingerprint(algorithm=algorithm, fingerprint=raw)
    raise ValueError(
        f"unrecognised fingerprint format: {raw!r}; "
        "expected 'SHA256:<base64>' or MD5 colon-separated hex"
    )


def fingerprint_from_public_key_bytes(
    algorithm: str, public_key_bytes: bytes
) -> HostKeyFingerprint:
    """Compute the canonical SHA-256 fingerprint for a public key blob."""
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"unsupported host key algorithm: {algorithm!r}")
    digest = hashlib.sha256(public_key_bytes).digest()
    body = base64.b64encode(digest).decode("ascii").rstrip("=")
    return HostKeyFingerprint(algorithm=algorithm, fingerprint=f"SHA256:{body}")


def fingerprints_match(a: HostKeyFingerprint, b: HostKeyFingerprint) -> bool:
    """Return True iff two fingerprints describe the same key.

    Comparison is algorithm-aware AND case-insensitive on the body. A
    mismatch on algorithm is always treated as "no match".
    """
    if a.algorithm != b.algorithm:
        return False
    if a.fingerprint == b.fingerprint:
        return True
    # Normalise: strip MD5 separators; lowercase base64 body.
    return _normalise(a.fingerprint) == _normalise(b.fingerprint)


def _normalise(fp: str) -> str:
    """Normalise a fingerprint string for comparison."""
    if fp.startswith("SHA256:"):
        return "SHA256:" + fp.split(":", 1)[1].lower().rstrip("=")
    # MD5 form
    return fp.lower().replace(":", "")


__all__ = [
    "SUPPORTED_ALGORITHMS",
    "HostKeyFingerprint",
    "fingerprint_from_public_key_bytes",
    "fingerprints_match",
    "parse_fingerprint",
]
