#!/usr/bin/env python3
"""Interactive script to add a credential to the VMAN vault and print its ID.

This allows you to create credential references to use in the Host setup form.
"""

from __future__ import annotations

import sys
import uuid
from sqlalchemy import select

from vman.config import get_settings
from vman.db import models
from vman.db.session import get_sessionmaker
from vman.security.crypto import decode_master_key_from_env
from vman.services.vault import Vault


def main() -> int:
    settings = get_settings()

    # 1. Resolve master key
    try:
        master_key_bytes = decode_master_key_from_env(settings.master_key)
    except Exception as exc:
        print(f"Error decoding VMAN_MASTER_KEY from environment: {exc}", file=sys.stderr)
        print("Please check your .env file.", file=sys.stderr)
        return 1

    session_factory = get_sessionmaker()

    # 2. Ensure an active encryption key is in the DB
    with session_factory() as session:
        active_key = session.execute(
            select(models.EncryptionKey)
            .where(models.EncryptionKey.status == "active")
            .limit(1)
        ).scalar_one_or_none()

        if active_key is None:
            print("No active encryption key found in database. Registering 'k-active'...")
            active_key = models.EncryptionKey(
                id="k-active",
                version=1,
                status="active"
            )
            session.add(active_key)
            session.commit()
            session.refresh(active_key)

        active_key_id = active_key.id

    # 3. Interactive inputs
    print("=== Add Vault Credential ===")
    name = input("Enter a display name (e.g. prod-server-key): ").strip()
    if not name:
        print("Name cannot be empty.")
        return 1

    print("\nSelect the credential kind:")
    print("1) ssh_password")
    print("2) ssh_private_key")
    print("3) ssh_private_key_passphrase")
    print("4) sudo_password")
    print("5) api_token")
    kind_choice = input("Enter choice (1-5) [default: 1]: ").strip() or "1"
    
    kinds = {
        "1": "ssh_password",
        "2": "ssh_private_key",
        "3": "ssh_private_key_passphrase",
        "4": "sudo_password",
        "5": "api_token"
    }
    kind = kinds.get(kind_choice, "ssh_password")

    print(f"\nEnter secret payload for kind '{kind}'.")
    print("Press Enter to input. For keys with multiple lines, just paste or input them directly:")
    secret_lines = []
    while True:
        try:
            line = input()
            secret_lines.append(line)
        except EOFError:
            break
        # If it's a password, a single line is expected, so we break after one line unless empty
        if kind in ("ssh_password", "sudo_password", "api_token") or not line:
            break
            
    plaintext = "\n".join(secret_lines).strip()
    if not plaintext:
        print("Secret payload cannot be empty.")
        return 1

    # 4. Create and store in the vault
    cred_id = str(uuid.uuid4())
    cred = models.Credential(
        id=cred_id,
        name=name,
        kind=kind,
        encrypted_payload=b"placeholder",
        encryption_key_id=active_key_id,
        fingerprint="",
        metadata_json={},
    )

    with session_factory() as session:
        # Check uniqueness of name
        existing_cred = session.execute(
            select(models.Credential).where(models.Credential.name == name)
        ).scalar_one_or_none()
        if existing_cred is not None:
            print(f"Error: A credential named '{name}' already exists.")
            return 1
        
        session.add(cred)
        session.commit()

    # Initialize vault and encrypt payload
    vault = Vault(master_key=master_key_bytes, session_factory=session_factory)
    vault.store(credential_id=cred_id, plaintext=plaintext, kind=kind)

    print("\n=== Credential Successfully Vaulted ===")
    print(f"Name: {name}")
    print(f"Kind: {kind}")
    print(f"Credential Reference ID (Paste this in the Host form):")
    print(f"\033[92m{cred_id}\033[0m")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
