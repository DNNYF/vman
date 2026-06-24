"""Tests for the AES-256-GCM crypto primitive (Milestone 0 / Task 3).

These tests exercise the raw encrypt/decrypt primitives, NOT the vault
service wrapper. They are the unit-level safety net that guarantees:

- Random nonces (no two encryptions of the same plaintext produce the
  same ciphertext, even with the same key).
- AAD (associated authenticated data) is bound to the ciphertext, so
  swapping the AAD between encrypt and decrypt MUST fail.
- Wrong key fails with an exception (cryptography raises
  InvalidTag, which we surface as CryptoError).
- Tampered ciphertext fails.
- Tampered AAD fails.
- Empty plaintext encrypts and round-trips.
"""

from __future__ import annotations

import pytest

from vman.security.crypto import (
    CryptoError,
    decrypt_bytes,
    encrypt_bytes,
    generate_master_key,
    key_fingerprint,
)


def _key() -> bytes:
    """Produce a fresh 32-byte key for each test (no cross-test leakage)."""
    return generate_master_key()


def test_generate_master_key_returns_32_bytes() -> None:
    key = generate_master_key()
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_generate_master_key_is_random() -> None:
    a = generate_master_key()
    b = generate_master_key()
    assert a != b


def test_encrypt_decrypt_round_trip() -> None:
    key = _key()
    plaintext = b"hello secret world"
    aad = b"credential-id:ssh_password:host-sg-1"
    ciphertext = encrypt_bytes(key, plaintext, aad=aad)
    assert plaintext not in ciphertext  # never include plaintext in output
    recovered = decrypt_bytes(key, ciphertext, aad=aad)
    assert recovered == plaintext


def test_encrypt_uses_random_nonce() -> None:
    key = _key()
    plaintext = b"same plaintext"
    aad = b"aad"
    c1 = encrypt_bytes(key, plaintext, aad=aad)
    c2 = encrypt_bytes(key, plaintext, aad=aad)
    # Same key, same plaintext, same AAD -- but random nonce -> different output.
    assert c1 != c2


def test_decrypt_with_wrong_key_raises() -> None:
    k1 = _key()
    k2 = _key()
    ciphertext = encrypt_bytes(k1, b"top secret", aad=b"x")
    with pytest.raises(CryptoError):
        decrypt_bytes(k2, ciphertext, aad=b"x")


def test_decrypt_with_wrong_aad_raises() -> None:
    key = _key()
    ciphertext = encrypt_bytes(key, b"top secret", aad=b"correct-aad")
    with pytest.raises(CryptoError):
        decrypt_bytes(key, ciphertext, aad=b"wrong-aad")


def test_tampered_ciphertext_raises() -> None:
    key = _key()
    ciphertext = encrypt_bytes(key, b"top secret", aad=b"a")
    # Flip the last byte (inside the GCM tag) -- must fail authentication.
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0x01])
    with pytest.raises(CryptoError):
        decrypt_bytes(key, tampered, aad=b"a")


def test_empty_plaintext_round_trip() -> None:
    key = _key()
    ciphertext = encrypt_bytes(key, b"", aad=b"empty")
    assert decrypt_bytes(key, ciphertext, aad=b"empty") == b""


def test_oversized_aad_is_rejected() -> None:
    key = _key()
    huge_aad = b"x" * (64 * 1024 + 1)  # GCM AAD limit is 64 KiB - 1 byte ish
    with pytest.raises((CryptoError, ValueError)):
        encrypt_bytes(key, b"payload", aad=huge_aad)


def test_key_fingerprint_is_stable_and_distinguishes_keys() -> None:
    k1 = _key()
    k2 = _key()
    f1 = key_fingerprint(k1)
    f2 = key_fingerprint(k2)
    assert f1 == key_fingerprint(k1)  # stable
    assert f1 != f2  # distinguishes different keys
    # Format: short hex (sha256 truncated) for display, NOT a secret.
    assert isinstance(f1, str)
    assert len(f1) >= 8


def test_ciphertext_has_version_byte() -> None:
    """Future-proofing: ciphertext starts with a version byte so we can
    introduce v2 (e.g. XChaCha20-Poly1305) without breaking old DB rows."""
    key = _key()
    ciphertext = encrypt_bytes(key, b"payload", aad=b"v")
    assert ciphertext[0] in (0x01,)  # v1 = AES-256-GCM
