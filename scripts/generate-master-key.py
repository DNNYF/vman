#!/usr/bin/env python3
"""Generate a fresh AES-256 master key for the VMAN credential vault.

Run once on the central VPS, then put the printed value in
``VMAN_MASTER_KEY`` inside ``/etc/vman/vman.env`` (or wherever the
operator keeps environment files). NEVER commit the printed value.

The output is URL-safe base64 so it survives shell quoting, .env
parsers, and copy-paste.
"""

from __future__ import annotations

import sys

from vman.security.crypto import (
    encode_master_key_for_env,
    generate_master_key,
    key_fingerprint,
)


def main() -> int:
    key = generate_master_key()
    encoded = encode_master_key_for_env(key)
    fingerprint = key_fingerprint(key)

    print("# VMAN master key (URL-safe base64, 32 raw bytes -> 44 chars)")
    print(f"VMAN_MASTER_KEY={encoded}")
    print(f"# fingerprint (non-secret, for display only): {fingerprint}")
    print("# Store in your env file; do NOT commit; do NOT log the value.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
