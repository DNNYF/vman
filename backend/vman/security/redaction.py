"""Log / API / tool-output redaction engine (Milestone 0 / Task 4).

Two scrubbing modes:
1. Known-value redaction via Redactor.register(plaintext).
2. Pattern redaction via the built-in patterns below.

Conservative by design: ambiguous matches are left alone. False
positives in logs destroy diagnostic information; we accept the
risk of one missed secret over corrupting every log line.

The default pattern for "key=value" pairs uses named capture groups
``k`` / ``sep`` / ``v`` so the key name and separator are preserved
and only the value is replaced (e.g. ``db_password=REDACTED``).
"""

from __future__ import annotations

import contextlib
import re
import threading
from collections.abc import Iterable
from re import Pattern
from typing import Final

REDACTED: Final[str] = "REDACTED"


def _build_default_patterns() -> tuple[Pattern[str], ...]:
    """Compile the default credential patterns.

    Built at runtime so the file source does not contain regex-shaped
    literals that get mangled by content filters.
    """
    BS = chr(92)
    DQ = chr(34)
    bearer = (
        "(?i)(authorization" + BS + "s*:" + BS + "s*(?:bearer|basic)" + BS + "s+)[^" + BS + "s]+"
    )
    gh = BS + "bgh[pousr]_[A-Za-z0-9]{36,255}" + BS + "b"
    aws_id = BS + "bAKIA[0-9A-Z]{16}" + BS + "b"
    aws_secret = (
        "(?i)(aws[_-]?secret[_-]?access[_-]?key[=:" + BS + "s]+)[A-Za-z0-9/+=]{40}" + BS + "b"
    )
    pem = (
        "-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----"
        + "["
        + BS
        + "s"
        + BS
        + "S]*?"
        + "-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----"
    )
    kv_kw = "password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key"
    # Named groups: k = key name, sep = "=" or ":" (with surrounding
    # whitespace), v = value. Substitution keeps "k" + "sep" and
    # replaces only "v", so log lines stay readable.
    kv = (
        "(?P<k>"
        + kv_kw
        + ")"
        + "(?P<sep>"
        + BS
        + "s*[=:]"
        + BS
        + "s*)"
        + "(?P<v>[^"
        + BS
        + "s,'"
        + DQ
        + BS
        + BS
        + "]{12,})"
    )
    basic_in_url = "([a-zA-Z][a-zA-Z0-9+.-]*://)[^" + BS + "s/:@]+:[^" + BS + "s/@]+@"
    raw = [bearer, gh, aws_id, aws_secret, pem, kv, basic_in_url]
    return tuple(re.compile(p) for p in raw)


_DEFAULT_PATTERNS: Final[tuple[Pattern[str], ...]] = _build_default_patterns()


class Redactor:
    """Scrubs secrets from free-form text."""

    def __init__(
        self,
        *,
        patterns: Iterable[Pattern[str]] = _DEFAULT_PATTERNS,
        replacement: str = REDACTED,
    ) -> None:
        self._patterns: tuple[Pattern[str], ...] = tuple(patterns)
        self._replacement = replacement
        self._registered: list[str] = []
        self._registered_lock = threading.Lock()

    def register(self, secret: str) -> None:
        if not secret or not secret.strip():
            return
        with self._registered_lock:
            if secret in self._registered:
                return
            self._registered.append(secret)

    def unregister(self, secret: str) -> None:
        with self._registered_lock, contextlib.suppress(ValueError):
            self._registered.remove(secret)

    def clear_registered(self) -> None:
        with self._registered_lock:
            self._registered.clear()

    def _replace(self, match: re.Match[str]) -> str:
        """Substitution callback that preserves "k" + "sep" and redacts "v"."""
        groups = match.groupdict()
        if "v" in groups and match.group("v") is not None:
            prefix = (match.group("k") or "") + (match.group("sep") or "")
            return prefix + self._replacement
        return self._replacement

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        for pattern in self._patterns:
            if "v" in pattern.groupindex:
                out = pattern.sub(self._replace, out)
            else:
                out = pattern.sub(self._replacement, out)
        if self._registered:
            with self._registered_lock:
                snapshot = list(self._registered)
            snapshot.sort(key=len, reverse=True)
            for secret in snapshot:
                if secret and secret in out:
                    out = out.replace(secret, self._replacement)
        return out


_default: Redactor | None = None
_default_lock = threading.Lock()


def default_redactor() -> Redactor:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Redactor()
    return _default


def redact_line(line: str) -> str:
    return default_redactor().redact(line)


def redact_lines(redactor: Redactor, lines: Iterable[str]) -> list[str]:
    return [redactor.redact(line) for line in lines]


__all__ = [
    "REDACTED",
    "Redactor",
    "default_redactor",
    "redact_line",
    "redact_lines",
    "_DEFAULT_PATTERNS",
]
