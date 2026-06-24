"""Integration tests for encrypted VMAN backup/export support."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from vman.cli.main import app
from vman.db import models
from vman.db.base import Base
from vman.security.crypto import generate_master_key
from vman.services.vault import Vault


@pytest.fixture()
def seeded_db(tmp_path: Path) -> dict[str, object]:
    db_path = tmp_path / "vman.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    master_key = generate_master_key()
    now = dt.datetime.now(dt.timezone.utc)
    credential_id = uuid.uuid4().hex
    host_id = uuid.uuid4().hex
    with SessionLocal() as session:
        session.add(models.EncryptionKey(id="key-1", version=1, status="active", created_at=now))
        session.add(
            models.Credential(
                id=credential_id,
                name="root-login",
                kind="ssh_password",
                encrypted_payload=b"placeholder",
                encryption_key_id="key-1",
                fingerprint="fp-public",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            models.Host(
                id=host_id,
                name="sg-backup-01",
                hostname_or_ip="10.23.45.67",
                ssh_port=22144,
                username="root",
                auth_method="password",
                credential_id=credential_id,
                environment="experiment",
                tags=["backup", "test"],
                notes="normal operational note",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    vault = Vault(master_key=master_key, session_factory=SessionLocal)
    vault.store(
        credential_id=credential_id,
        plaintext="ultra-private-ssh-password",
        kind="ssh_password",
    )
    engine.dispose()
    return {
        "db_path": db_path,
        "master_key": master_key,
        "credential_id": credential_id,
        "host_id": host_id,
    }


def test_encrypted_database_backup_round_trips_without_plaintext(tmp_path: Path, seeded_db) -> None:
    from vman.services.backup import BackupService

    backup_path = tmp_path / "backup.vmanbak"
    restore_path = tmp_path / "restored.db"
    service = BackupService(master_key=seeded_db["master_key"])

    manifest = service.create_database_backup(
        database_path=seeded_db["db_path"],
        output_path=backup_path,
    )

    assert manifest["kind"] == "database"
    assert backup_path.exists()
    backup_bytes = backup_path.read_bytes()
    assert b"sg-backup-01" not in backup_bytes
    assert b"10.23.45.67" not in backup_bytes
    assert b"ultra-private-ssh-password" not in backup_bytes

    restored_manifest = service.restore_database_backup(
        backup_path=backup_path,
        output_path=restore_path,
    )
    assert restored_manifest["kind"] == "database"
    restored_engine = create_engine(f"sqlite:///{restore_path}", future=True)
    with sessionmaker(bind=restored_engine, future=True)() as session:
        host = session.execute(
            select(models.Host).where(models.Host.id == seeded_db["host_id"])
        ).scalar_one()
        assert host.name == "sg-backup-01"
        cred = session.execute(
            select(models.Credential).where(models.Credential.id == seeded_db["credential_id"])
        ).scalar_one()
        assert bytes(cred.encrypted_payload) != b"ultra-private-ssh-password"
    restored_engine.dispose()


def test_encrypted_host_inventory_export_excludes_plaintext_and_credential_payload(
    tmp_path: Path, seeded_db
) -> None:
    from vman.services.backup import BackupService

    export_path = tmp_path / "hosts.vmanexport"
    service = BackupService(master_key=seeded_db["master_key"])

    manifest = service.create_host_inventory_export(
        database_path=seeded_db["db_path"],
        output_path=export_path,
    )

    assert manifest["kind"] == "host_inventory"
    raw = export_path.read_bytes()
    assert b"sg-backup-01" not in raw
    assert b"10.23.45.67" not in raw
    assert b"ultra-private-ssh-password" not in raw
    assert b"encrypted_payload" not in raw

    payload = service.load_host_inventory_export(export_path)
    assert payload["schema_version"] == 1
    assert payload["hosts"][0]["name"] == "sg-backup-01"
    assert payload["hosts"][0]["credential_id"] == seeded_db["credential_id"]
    assert "encrypted_payload" not in payload["hosts"][0]


def test_backup_validation_rejects_tampered_file(tmp_path: Path, seeded_db) -> None:
    from vman.services.backup import BackupError, BackupService

    backup_path = tmp_path / "backup.vmanbak"
    service = BackupService(master_key=seeded_db["master_key"])
    service.create_database_backup(database_path=seeded_db["db_path"], output_path=backup_path)

    data = bytearray(backup_path.read_bytes())
    data[-8] ^= 1
    backup_path.write_bytes(bytes(data))

    with pytest.raises(BackupError):
        service.restore_database_backup(backup_path=backup_path, output_path=tmp_path / "bad.db")


def test_vmanctl_local_backup_export_restore_commands(tmp_path: Path, seeded_db) -> None:
    key_text = base64.urlsafe_b64encode(seeded_db["master_key"]).decode("ascii")
    backup_path = tmp_path / "cli-backup.vmanbak"
    export_path = tmp_path / "cli-hosts.vmanexport"
    restore_path = tmp_path / "cli-restored.db"
    runner = CliRunner()
    env = {
        **os.environ,
        "VMAN_MASTER_KEY": key_text,
        "VMAN_DATABASE_URL": f"sqlite:///{seeded_db['db_path']}",
        "VMAN_DOTENV_PATH": "/dev/null",
    }

    backup_result = runner.invoke(app, ["backup", "create", "--output", str(backup_path)], env=env)
    assert backup_result.exit_code == 0, backup_result.stdout + backup_result.stderr
    assert backup_path.exists()

    export_result = runner.invoke(app, ["export", "hosts", "--output", str(export_path)], env=env)
    assert export_result.exit_code == 0, export_result.stdout + export_result.stderr
    assert export_path.exists()
    assert "sg-backup-01" not in export_result.stdout

    restore_result = runner.invoke(
        app,
        ["restore", "database", str(backup_path), "--output", str(restore_path)],
        env=env,
    )
    assert restore_result.exit_code == 0, restore_result.stdout + restore_result.stderr
    assert restore_path.exists()

    verify = json.loads(runner.invoke(app, ["backup", "inspect", str(backup_path)], env=env).stdout)
    assert verify["kind"] == "database"
