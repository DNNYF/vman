"""Encrypted backup and export support for VMAN.

Backups use the same AES-256-GCM primitives as the credential vault and
therefore require the operator-supplied VMAN master key for both creation
and restore. The master key is never written to the backup file.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Final

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from vman.db import models
from vman.security.crypto import CryptoError, decrypt_bytes, encrypt_bytes, key_fingerprint

_BACKUP_MAGIC: Final[bytes] = b"VMAN-BACKUP\n"
_BACKUP_AAD: Final[bytes] = b"vman:backup:v1"
_EXPORT_AAD: Final[bytes] = b"vman:host-inventory-export:v1"
_SCHEMA_VERSION: Final[int] = 1


class BackupError(Exception):
    """Raised when encrypted backup/export operations fail safely."""


class BackupService:
    """Create and load encrypted VMAN backup artifacts."""

    def __init__(self, *, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise BackupError("master key must be exactly 32 bytes")
        self._master_key = master_key

    def create_database_backup(
        self, *, database_path: Path | str, output_path: Path | str
    ) -> dict[str, Any]:
        """Encrypt a consistent SQLite database snapshot to ``output_path``."""

        source = Path(database_path)
        target = Path(output_path)
        if not source.exists():
            raise BackupError("database file does not exist")
        snapshot = self._copy_sqlite_snapshot(source)
        try:
            plaintext = snapshot.read_bytes()
        finally:
            snapshot.unlink(missing_ok=True)
        manifest = self._manifest(kind="database", plaintext=plaintext, source=source)
        self._write_envelope(target, manifest=manifest, plaintext=plaintext, aad=_BACKUP_AAD)
        return manifest

    def restore_database_backup(
        self, *, backup_path: Path | str, output_path: Path | str
    ) -> dict[str, Any]:
        """Decrypt and validate a database backup into ``output_path``."""

        source = Path(backup_path)
        target = Path(output_path)
        manifest, plaintext = self._read_envelope(source, aad=_BACKUP_AAD)
        if manifest.get("kind") != "database":
            raise BackupError("backup file is not a database backup")
        self._validate_digest(manifest, plaintext)
        with tempfile.NamedTemporaryFile(prefix="vman-restore-", suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(plaintext)
        try:
            self._validate_sqlite_database(tmp_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return manifest

    def inspect_backup(self, backup_path: Path | str) -> dict[str, Any]:
        """Return authenticated backup metadata without writing restored data."""

        source = Path(backup_path)
        last_error: Exception | None = None
        for aad in (_BACKUP_AAD, _EXPORT_AAD):
            try:
                manifest, plaintext = self._read_envelope(source, aad=aad)
                self._validate_digest(manifest, plaintext)
                return manifest
            except BackupError as exc:
                last_error = exc
        raise BackupError("backup validation failed") from last_error

    def create_host_inventory_export(
        self, *, database_path: Path | str, output_path: Path | str
    ) -> dict[str, Any]:
        """Write an encrypted export containing host inventory but no credential payloads."""

        payload = self._host_inventory_payload(Path(database_path))
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest = self._manifest(
            kind="host_inventory",
            plaintext=plaintext,
            source=Path(database_path),
            extra={"host_count": len(payload["hosts"])},
        )
        self._write_envelope(
            Path(output_path),
            manifest=manifest,
            plaintext=plaintext,
            aad=_EXPORT_AAD,
        )
        return manifest

    def load_host_inventory_export(self, export_path: Path | str) -> dict[str, Any]:
        """Decrypt and validate a host inventory export."""

        manifest, plaintext = self._read_envelope(Path(export_path), aad=_EXPORT_AAD)
        if manifest.get("kind") != "host_inventory":
            raise BackupError("backup file is not a host inventory export")
        self._validate_digest(manifest, plaintext)
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("host inventory export is not valid JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
            raise BackupError("unsupported host inventory export schema")
        hosts = payload.get("hosts")
        if not isinstance(hosts, list):
            raise BackupError("host inventory export is missing hosts")
        for host in hosts:
            if not isinstance(host, dict) or "encrypted_payload" in host:
                raise BackupError("host inventory export contains invalid host data")
        return payload

    def _copy_sqlite_snapshot(self, source: Path) -> Path:
        with tempfile.NamedTemporaryFile(prefix="vman-backup-", suffix=".db", delete=False) as tmp:
            snapshot = Path(tmp.name)
        try:
            source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            try:
                dest_conn = sqlite3.connect(snapshot)
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()
        except sqlite3.Error:
            snapshot.unlink(missing_ok=True)
            with tempfile.NamedTemporaryFile(
                prefix="vman-backup-copy-",
                suffix=".db",
                delete=False,
            ) as tmp:
                snapshot = Path(tmp.name)
            shutil.copy2(source, snapshot)
        return snapshot

    def _manifest(
        self,
        *,
        kind: str,
        plaintext: bytes,
        source: Path,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "kind": kind,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cipher": "AES-256-GCM",
            "key_fingerprint": key_fingerprint(self._master_key),
            "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            "plaintext_bytes": len(plaintext),
            "source_name": source.name,
        }
        if extra:
            manifest.update(extra)
        return manifest

    def _write_envelope(
        self,
        target: Path,
        *,
        manifest: dict[str, Any],
        plaintext: bytes,
        aad: bytes,
    ) -> None:
        envelope = {
            "format": "vman.encrypted-backup",
            "manifest": manifest,
            "ciphertext": encrypt_bytes(
                self._master_key,
                plaintext,
                aad=_aad_for_manifest(aad, manifest),
            ).hex(),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_BACKUP_MAGIC + json.dumps(envelope, sort_keys=True).encode("utf-8"))
        with contextlib.suppress(OSError):
            target.chmod(0o600)

    def _read_envelope(self, source: Path, *, aad: bytes) -> tuple[dict[str, Any], bytes]:
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise BackupError("backup file could not be read") from exc
        if not raw.startswith(_BACKUP_MAGIC):
            raise BackupError("backup file has an unsupported format")
        try:
            envelope = json.loads(raw[len(_BACKUP_MAGIC) :].decode("utf-8"))
            manifest = envelope["manifest"]
            ciphertext = bytes.fromhex(envelope["ciphertext"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("backup file metadata is invalid") from exc
        if not isinstance(manifest, dict):
            raise BackupError("backup file manifest is invalid")
        try:
            plaintext = decrypt_bytes(
                self._master_key,
                ciphertext,
                aad=_aad_for_manifest(aad, manifest),
            )
        except CryptoError as exc:
            raise BackupError("backup decryption failed") from exc
        return manifest, plaintext

    def _validate_digest(self, manifest: dict[str, Any], plaintext: bytes) -> None:
        expected = manifest.get("plaintext_sha256")
        actual = hashlib.sha256(plaintext).hexdigest()
        if not isinstance(expected, str) or not secrets_equal(expected, actual):
            raise BackupError("backup integrity check failed")

    def _validate_sqlite_database(self, path: Path) -> None:
        try:
            conn = sqlite3.connect(path)
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise BackupError("restored backup is not a valid SQLite database") from exc
        if not result or result[0] != "ok":
            raise BackupError("restored backup failed SQLite integrity check")

    def _host_inventory_payload(self, database_path: Path) -> dict[str, Any]:
        if not database_path.exists():
            raise BackupError("database file does not exist")
        engine = create_engine(f"sqlite:///{database_path}", future=True)
        SessionLocal = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        try:
            with SessionLocal() as session:
                hosts = (
                    session.execute(select(models.Host).order_by(models.Host.name))
                    .scalars()
                    .all()
                )
                return {
                    "schema_version": _SCHEMA_VERSION,
                    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "hosts": [self._host_to_export(host, session) for host in hosts],
                }
        finally:
            engine.dispose()

    def _host_to_export(self, host: models.Host, session: Session) -> dict[str, Any]:
        credential_fingerprint = None
        if host.credential_id:
            credential = session.get(models.Credential, host.credential_id)
            if credential is not None:
                credential_fingerprint = credential.fingerprint
        return {
            "id": host.id,
            "name": host.name,
            "hostname_or_ip": host.hostname_or_ip,
            "ssh_port": host.ssh_port,
            "username": host.username,
            "auth_method": host.auth_method,
            "credential_id": host.credential_id,
            "credential_fingerprint": credential_fingerprint,
            "tags": list(host.tags or []),
            "environment": host.environment,
            "notes": host.notes,
            "created_at": _iso_or_none(host.created_at),
            "updated_at": _iso_or_none(host.updated_at),
        }


def _iso_or_none(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _aad_for_manifest(base: bytes, manifest: dict[str, Any]) -> bytes:
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return base + b"|" + hashlib.sha256(manifest_bytes).hexdigest().encode("ascii")


def secrets_equal(left: str, right: str) -> bool:
    """Small constant-time-ish string comparison."""

    return hashlib.sha256(left.encode()).digest() == hashlib.sha256(right.encode()).digest()


__all__ = ["BackupError", "BackupService"]
