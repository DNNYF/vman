"""Tests for the credential vault service (Milestone 0 / Task 3).

These tests exercise the ``Vault`` service wrapper around the raw
``crypto`` primitives. The wrapper is responsible for:

- Choosing the right ``EncryptionKey`` row (currently always the active
  one; rotation-aware selection is added when we introduce DEK wrapping
  in a later task).
- Building the correct AAD from credential id + kind so a ciphertext
  bound to one credential cannot be replayed against another.
- Wrapping low-level CryptoError into a domain exception.
- Never logging or echoing plaintext or ciphertext values.

The vault never returns plaintext to a caller in a host-CPU-readable
way unless explicitly asked; even when asked, it MUST do so only inside
the worker process. In the MVP we keep the API simple: the vault
returns the plaintext when ``reveal()`` is called, and the worker is
the only consumer.
"""

from __future__ import annotations

import secrets
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from vman.db import models
from vman.db.base import Base
from vman.security.crypto import CryptoError, generate_master_key
from vman.services.vault import Vault, VaultError


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def vault(session_factory) -> Vault:
    # Register an active EncryptionKey row so the vault has a valid key id.
    key_bytes = generate_master_key()
    with session_factory() as s:
        s.add(models.EncryptionKey(id="k-active", version=1, status="active"))
        s.commit()
    return Vault(master_key=key_bytes, session_factory=session_factory)


def _seed_credential(session_factory, *, name: str = "host-sg-1") -> models.Credential:
    cred = models.Credential(
        id=str(uuid.uuid4()),
        name=name,
        kind="ssh_password",
        # placeholder ciphertext so we can construct; vault encrypts on store
        encrypted_payload=b"placeholder",
        encryption_key_id="k-active",
        fingerprint="",
        metadata_json={},
    )
    with session_factory() as s:
        s.add(cred)
        s.commit()
        s.refresh(cred)
    return cred


def test_store_writes_ciphertext_not_plaintext(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    plaintext = "super-secret-ssh-password"

    stored = vault.store(
        credential_id=cred.id,
        plaintext=plaintext,
        kind="ssh_password",
    )

    assert stored.id == cred.id
    # The on-disk payload must NOT contain the plaintext.
    assert plaintext.encode() not in stored.encrypted_payload
    # The plaintext, once recovered, must equal what we stored.
    revealed = vault.reveal(credential_id=cred.id)
    assert revealed == plaintext


def test_store_persists_fingerprint(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    vault.store(
        credential_id=cred.id,
        plaintext="another-secret",
        kind="ssh_password",
        public_fingerprint="sha256:abcd1234",
    )
    with session_factory() as s:
        row = s.execute(
            select(models.Credential).where(models.Credential.id == cred.id)
        ).scalar_one()
    assert row.fingerprint == "sha256:abcd1234"


def test_reveal_with_no_stored_payload_raises(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    # We never called vault.store -- encrypted_payload is the placeholder bytes.
    with pytest.raises(VaultError):
        vault.reveal(credential_id=cred.id)


def test_aad_is_bound_to_credential(vault, session_factory) -> None:
    """A ciphertext stored for credential A MUST NOT decrypt as credential B."""
    cred_a = _seed_credential(session_factory, name="a")
    cred_b = _seed_credential(session_factory, name="b")
    vault.store(credential_id=cred_a.id, plaintext="top-secret", kind="ssh_password")

    # Direct decryption with cred_b's AAD must fail.
    from vman.security.crypto import decrypt_bytes

    with session_factory() as s:
        row = s.execute(
            select(models.Credential).where(models.Credential.id == cred_a.id)
        ).scalar_one()
        ciphertext = bytes(row.encrypted_payload)

    wrong_aad = f"credential_id={cred_b.id}|kind=ssh_password".encode()
    with pytest.raises(CryptoError):
        decrypt_bytes(vault._master_key, ciphertext, aad=wrong_aad)


def test_vault_rejects_wrong_master_key_on_reveal(session_factory) -> None:
    # Seed with key A
    key_a = generate_master_key()
    with session_factory() as s:
        s.add(models.EncryptionKey(id="k-active", version=1, status="active"))
        s.commit()
    vault_a = Vault(master_key=key_a, session_factory=session_factory)
    cred = _seed_credential(session_factory)
    vault_a.store(credential_id=cred.id, plaintext="x", kind="ssh_password")

    # Now build a vault with a different key. Reveal MUST fail.
    key_b = generate_master_key()
    vault_b = Vault(master_key=key_b, session_factory=session_factory)
    with pytest.raises(VaultError):
        vault_b.reveal(credential_id=cred.id)


def test_store_overwrites_previous_ciphertext(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    vault.store(credential_id=cred.id, plaintext="first", kind="ssh_password")
    vault.store(credential_id=cred.id, plaintext="second", kind="ssh_password")
    assert vault.reveal(credential_id=cred.id) == "second"


def test_reveal_returns_str_for_known_kind(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    vault.store(
        credential_id=cred.id,
        plaintext="unicode-check: éèê",
        kind="ssh_password",
    )
    revealed = vault.reveal(credential_id=cred.id)
    assert isinstance(revealed, str)
    assert revealed == "unicode-check: éèê"


def test_vault_handles_large_payloads(vault, session_factory) -> None:
    cred = _seed_credential(session_factory)
    big = secrets.token_hex(50_000)  # 100 KB
    vault.store(credential_id=cred.id, plaintext=big, kind="ssh_private_key")
    assert vault.reveal(credential_id=cred.id) == big
