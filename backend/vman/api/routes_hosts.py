"""Host inventory HTTP routes (Milestone 2 / Task 8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from vman.api.deps import CurrentUser
from vman.config import get_settings
from vman.db import models
from vman.db.session import get_sessionmaker
from vman.schemas.hosts import HostCreate, HostOut, HostUpdate, ConnectionTestResult
from vman.security.audit import AuditService
from vman.security.csrf import require_csrf
from vman.security.redaction import default_redactor
from vman.services.hosts import HostService, HostServiceError
from vman.services.vault import Vault
from vman.services.ssh_runner import SshRunner, ParamikoTransport
from vman.security.host_keys import parse_fingerprint

router = APIRouter(prefix="/api/hosts", tags=["hosts"])



def _service() -> HostService:
    return HostService(
        session_factory=get_sessionmaker(),
        audit=AuditService(
            session_factory=get_sessionmaker(),
            redactor=default_redactor(),
        ),
    )


def _to_out(host: models.Host) -> HostOut:
    return HostOut(
        id=host.id,
        name=host.name,
        hostname_or_ip=host.hostname_or_ip,
        ssh_port=host.ssh_port,
        username=host.username,
        auth_method=host.auth_method,
        credential_id=host.credential_id,
        sudo_mode=host.sudo_mode,
        host_key_fingerprint=host.host_key_fingerprint,
        host_key_algorithm=host.host_key_algorithm,
        os_family=host.os_family,
        os_name=host.os_name,
        os_version=host.os_version,
        package_manager=host.package_manager,
        arch=host.arch,
        cpu_cores=host.cpu_cores,
        ram_mb=host.ram_mb,
        disk_total_mb=host.disk_total_mb,
        provider=host.provider,
        region=host.region,
        environment=host.environment,
        risk_level=host.risk_level,
        tags=list(host.tags or []),
        notes=host.notes,
        last_seen_at=host.last_seen_at.isoformat() if host.last_seen_at else None,
        disabled_at=host.disabled_at.isoformat() if host.disabled_at else None,
        created_at=host.created_at.isoformat() if host.created_at else "",
        updated_at=host.updated_at.isoformat() if host.updated_at else "",
    )


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #


@router.get("", response_model=list[HostOut])
def list_hosts(
    user: CurrentUser,
    include_disabled: bool = False,
) -> list[HostOut]:
    rows = _service().list_hosts(include_disabled=include_disabled)
    return [_to_out(r) for r in rows]


# --------------------------------------------------------------------------- #
# Get
# --------------------------------------------------------------------------- #


@router.get("/{host_id}", response_model=HostOut)
def get_host(host_id: str, user: CurrentUser) -> HostOut:
    row = _service().get(host_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="host not found")
    return _to_out(row)


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #


@router.post("", response_model=HostOut, status_code=status.HTTP_201_CREATED)
def create_host(
    payload: HostCreate,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> HostOut:
    try:
        host = _service().create(
            name=payload.name,
            hostname_or_ip=payload.hostname_or_ip,
            ssh_port=payload.ssh_port,
            username=payload.username,
            auth_method=payload.auth_method,
            actor_user_id=user.id,
            credential_id=payload.credential_id,
            sudo_mode=payload.sudo_mode,
            environment=payload.environment,
            provider=payload.provider,
            region=payload.region,
            tags=payload.tags,
            notes=payload.notes,
        )
    except HostServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_out(host)


# --------------------------------------------------------------------------- #
# Update (partial)
# --------------------------------------------------------------------------- #


@router.patch("/{host_id}", response_model=HostOut)
def update_host(
    host_id: str,
    payload: HostUpdate,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> HostOut:
    update_data = payload.model_dump(exclude_unset=True)
    try:
        host = _service().update(host_id=host_id, actor_user_id=user.id, **update_data)
    except HostServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_out(host)


# --------------------------------------------------------------------------- #
# Delete (soft)
# --------------------------------------------------------------------------- #


@router.delete("/{host_id}")
def delete_host(
    host_id: str,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> dict[str, str]:
    try:
        _service().delete(host_id=host_id, actor_user_id=user.id)
    except HostServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Connection Test
# --------------------------------------------------------------------------- #


@router.post("/{host_id}/test", response_model=ConnectionTestResult)
def test_connection(
    host_id: str,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> ConnectionTestResult:
    import time
    import datetime as dt
    from vman.security.crypto import decode_master_key_from_env

    # 1. Get host
    service = _service()
    host = service.get(host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found")

    tested_at = dt.datetime.now(dt.timezone.utc).isoformat()

    # 2. Get credentials from Vault
    password = None
    private_key = None
    passphrase = None

    if host.credential_id:
        settings = get_settings()
        try:
            master_key_bytes = decode_master_key_from_env(settings.master_key)
            vault = Vault(master_key=master_key_bytes, session_factory=get_sessionmaker())
            plaintext = vault.reveal(credential_id=host.credential_id)

            with get_sessionmaker()() as db_session:
                cred = db_session.get(models.Credential, host.credential_id)
                if cred:
                    if cred.kind == "ssh_password":
                        password = plaintext
                    elif cred.kind == "ssh_private_key":
                        private_key = plaintext
                    elif cred.kind == "ssh_private_key_passphrase":
                        # If a key passphrase is provided, we treat it as passphrase and private key.
                        # For the MVP, if the host method is key, we treat plaintext as private key.
                        # If auth method is key_with_passphrase, we can handle it or use a default.
                        if host.auth_method == "password":
                            password = plaintext
                        else:
                            private_key = plaintext
                    else:
                        # Fallback for other credential types (e.g. sudo_password, api_token)
                        if host.auth_method == "password":
                            password = plaintext
                        elif host.auth_method in ("key", "key_with_passphrase"):
                            private_key = plaintext
        except Exception as exc:
            return ConnectionTestResult(
                ok=False,
                reached=False,
                authenticated=False,
                message=f"Failed to retrieve or decrypt credential: {exc}",
                tested_at=tested_at,
            )

    # 3. Perform connection test
    transport = ParamikoTransport(password=password, private_key=private_key, passphrase=passphrase)

    expected_fp = None
    if host.host_key_fingerprint and host.host_key_algorithm:
        try:
            expected_fp = parse_fingerprint(host.host_key_algorithm, host.host_key_fingerprint)
        except Exception:
            pass

    runner = SshRunner(
        transport=transport,
        host=host.hostname_or_ip,
        port=host.ssh_port,
        username=host.username,
        expected_fingerprint=expected_fp,
    )

    start_time = time.time()
    try:
        # Run a simple echo command to test connection
        result = runner.run("echo 'ping'", timeout=10.0)
        latency = (time.time() - start_time) * 1000.0

        server_key = transport.server_host_key()

        # Automatically store host key fingerprint on successful first connection
        if not host.host_key_fingerprint:
            service.update(
                host_id=host.id,
                actor_user_id=user.id,
                host_key_fingerprint=server_key.fingerprint,
                host_key_algorithm=server_key.algorithm,
            )

        if result.exit_code == 0:
            # ── Gather OS information ──────────────────────────────────────
            os_update: dict = {}
            try:
                def _run(cmd: str) -> str:
                    r = runner.run(cmd, timeout=10.0)
                    return r.stdout.strip() if r.exit_code == 0 else ""

                raw_id = _run(
                    "cat /etc/os-release 2>/dev/null || "
                    "cat /usr/lib/os-release 2>/dev/null || echo ''"
                )

                def _field(key: str) -> str:
                    for line in raw_id.splitlines():
                        if line.startswith(f"{key}="):
                            return line.split("=", 1)[1].strip().strip('"')
                    return ""

                detected_name    = _field("NAME") or _field("ID")
                detected_version = _field("VERSION_ID") or _field("VERSION")
                pkg_mgr = ""
                for pm in ("apt", "yum", "dnf", "zypper", "apk", "pacman"):
                    if _run(f"command -v {pm}"):
                        pkg_mgr = pm
                        break

                arch_str   = _run("uname -m")
                cpu_str    = _run(
                    "nproc 2>/dev/null || "
                    "grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo ''"
                )
                ram_str    = _run(
                    "awk '/MemTotal/{printf \"%d\", $2/1024}' /proc/meminfo 2>/dev/null || echo ''"
                )
                disk_str   = _run(
                    "df / --output=size -B 1M 2>/dev/null | tail -1 | tr -d ' ' || echo ''"
                )

                os_update = dict(
                    os_name         = detected_name or None,
                    os_version      = detected_version or None,
                    arch            = arch_str or None,
                    package_manager = pkg_mgr or None,
                    cpu_cores       = int(cpu_str) if cpu_str.isdigit() else None,
                    ram_mb          = int(ram_str) if ram_str.isdigit() else None,
                    disk_total_mb   = int(disk_str) if disk_str.isdigit() else None,
                    last_seen_at    = dt.datetime.now(dt.timezone.utc),
                )
            except Exception:
                # OS detection is best-effort; never block a successful test
                pass

            # Persist host key + OS info
            service.update(
                host_id=host.id,
                actor_user_id=user.id,
                host_key_fingerprint=server_key.fingerprint,
                host_key_algorithm=server_key.algorithm,
                **os_update,
            )

            return ConnectionTestResult(
                ok=True,
                reached=True,
                authenticated=True,
                host_key_fingerprint=server_key.fingerprint,
                host_key_algorithm=server_key.algorithm,
                latency_ms=latency,
                message="Successfully connected and authenticated.\n" + (result.stdout or ""),
                tested_at=tested_at,
            )
        else:
            return ConnectionTestResult(
                ok=False,
                reached=True,
                authenticated=True,
                host_key_fingerprint=server_key.fingerprint,
                host_key_algorithm=server_key.algorithm,
                latency_ms=latency,
                message=f"Connected but command failed with code {result.exit_code}: {result.stderr}",
                tested_at=tested_at,
            )
    except Exception as exc:
        latency = (time.time() - start_time) * 1000.0
        message = str(exc)
        
        # Determine error reason
        reached = "authentication failed" not in message.lower() and "permission denied" not in message.lower()
        authenticated = not reached

        fk_fp = None
        fk_alg = None
        try:
            server_key = transport.server_host_key()
            fk_fp = server_key.fingerprint
            fk_alg = server_key.algorithm
        except Exception:
            pass

        return ConnectionTestResult(
            ok=False,
            reached=reached,
            authenticated=authenticated,
            host_key_fingerprint=fk_fp,
            host_key_algorithm=fk_alg,
            latency_ms=latency if reached else None,
            message=f"Connection failed: {message}",
            tested_at=tested_at,
        )


__all__ = ["router"]

