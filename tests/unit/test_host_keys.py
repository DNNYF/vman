"""Unit tests for the host key fingerprint helpers (Milestone 2 / Task 9)."""

from __future__ import annotations

import base64

import pytest

from vman.security.host_keys import (
    SUPPORTED_ALGORITHMS,
    HostKeyFingerprint,
    fingerprint_from_public_key_bytes,
    fingerprints_match,
    parse_fingerprint,
)


def test_parse_accepts_sha256_form() -> None:
    fp = parse_fingerprint("ssh-ed25519", "SHA256:" + "a" * 43)
    assert fp.algorithm == "ssh-ed25519"
    assert fp.fingerprint == "SHA256:" + "a" * 43


def test_parse_accepts_md5_form() -> None:
    raw = ":".join(["ab"] * 16)
    fp = parse_fingerprint("ssh-rsa", raw)
    assert fp.algorithm == "ssh-rsa"
    assert fp.fingerprint == raw


def test_parse_rejects_unsupported_algorithm() -> None:
    with pytest.raises(ValueError):
        parse_fingerprint("not-a-real-alg", "SHA256:" + "a" * 43)


def test_parse_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_fingerprint("ssh-ed25519", "")


def test_parse_rejects_garbage_format() -> None:
    with pytest.raises(ValueError):
        parse_fingerprint("ssh-ed25519", "not-a-fingerprint")
    with pytest.raises(ValueError):
        parse_fingerprint("ssh-ed25519", "SHA256:not_base64!@")


def test_fingerprint_from_public_key_bytes_deterministic() -> None:
    blob = b"some-public-key-bytes"
    a = fingerprint_from_public_key_bytes("ssh-ed25519", blob)
    b = fingerprint_from_public_key_bytes("ssh-ed25519", blob)
    assert a == b
    assert a.fingerprint.startswith("SHA256:")


def test_fingerprint_changes_with_key() -> None:
    a = fingerprint_from_public_key_bytes("ssh-ed25519", b"key-a")
    b = fingerprint_from_public_key_bytes("ssh-ed25519", b"key-b")
    assert a != b


def test_fingerprint_uses_canonical_base64() -> None:
    """Base64 must round-trip; the body must be valid base64."""
    fp = fingerprint_from_public_key_bytes("ssh-ed25519", b"hello")
    body = fp.fingerprint.split(":", 1)[1]
    # Add padding then decode.
    padded = body + "=" * (-len(body) % 4)
    raw = base64.b64decode(padded)
    assert len(raw) == 32  # SHA-256 = 32 bytes


def test_match_same() -> None:
    a = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    b = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    assert fingerprints_match(a, b)


def test_match_different_algorithm() -> None:
    a = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    b = HostKeyFingerprint(algorithm="ssh-rsa", fingerprint="SHA256:abc")
    assert not fingerprints_match(a, b)


def test_match_different_body() -> None:
    a = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    b = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:xyz")
    assert not fingerprints_match(a, b)


def test_match_case_insensitive_on_base64() -> None:
    a = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:ABC")
    b = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    assert fingerprints_match(a, b)


def test_match_md5_form_normalised() -> None:
    a = HostKeyFingerprint(
        algorithm="ssh-rsa", fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
    )
    b = HostKeyFingerprint(
        algorithm="ssh-rsa", fingerprint="AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
    )
    assert fingerprints_match(a, b)


def test_supported_algorithms_includes_modern_set() -> None:
    # Must include ed25519 and the modern RSA variants.
    assert "ssh-ed25519" in SUPPORTED_ALGORITHMS
    assert "rsa-sha2-512" in SUPPORTED_ALGORITHMS
    assert "rsa-sha2-256" in SUPPORTED_ALGORITHMS


def test_str_round_trip() -> None:
    fp = HostKeyFingerprint(algorithm="ssh-ed25519", fingerprint="SHA256:abc")
    s = str(fp)
    assert "ssh-ed25519" in s
    assert "SHA256:abc" in s


def test_parse_then_match_round_trip() -> None:
    raw = fingerprint_from_public_key_bytes("ssh-ed25519", b"data")
    parsed = parse_fingerprint(raw.algorithm, raw.fingerprint)
    assert fingerprints_match(raw, parsed)
