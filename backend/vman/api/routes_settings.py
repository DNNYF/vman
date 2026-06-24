"""Application settings API routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from vman.api.deps import CurrentUser
from vman.config import Settings, get_settings, _resolve_dotenv_path

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    env: str
    api_host: str
    api_port: int
    database_url: str
    log_level: str
    log_retention_days: int
    metrics_retention_days: int
    uvicorn_workers: int
    worker_concurrency: int
    ssh_connect_timeout_seconds: int
    ssh_command_timeout_seconds: int


class SettingsUpdateRequest(BaseModel):
    env: Literal["development", "production"] | None = None
    api_host: str | None = None
    api_port: int | None = None
    database_url: str | None = None
    log_level: str | None = None
    log_retention_days: int | None = None
    metrics_retention_days: int | None = None
    uvicorn_workers: int | None = None
    worker_concurrency: int | None = None
    ssh_connect_timeout_seconds: int | None = None
    ssh_command_timeout_seconds: int | None = None


def update_dotenv(updates: dict[str, Any]) -> None:
    """Read and parse existing .env file in workspace root, update matching VMAN_* variables, and write back."""
    dotenv_path = _resolve_dotenv_path()
    if dotenv_path is None:
        dotenv_path = Path.cwd() / ".env"

    content = ""
    if dotenv_path.exists():
        content = dotenv_path.read_text(encoding="utf-8")

    lines = content.splitlines()
    new_lines = []
    updated_keys = set()

    # Convert updates keys to upper case VMAN_* format
    normalized_updates = {}
    for k, v in updates.items():
        if v is None:
            continue
        ukey = k.upper()
        if not ukey.startswith("VMAN_"):
            ukey = f"VMAN_{ukey}"
        normalized_updates[ukey] = str(v)

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key, sep, val = line.partition("=")
        key_strip = key.strip()
        if key_strip in normalized_updates:
            new_lines.append(f"{key_strip}={normalized_updates[key_strip]}")
            updated_keys.add(key_strip)
        else:
            new_lines.append(line)

    for k, v in normalized_updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")

    # Write back to .env
    dotenv_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Reload into os.environ
    for k, v in normalized_updates.items():
        os.environ[k] = v

    # Clear Settings LRU cache
    get_settings.cache_clear()


@router.get("", response_model=SettingsResponse)
def get_current_settings(user: CurrentUser) -> SettingsResponse:
    """Retrieve safe application configuration values."""
    settings = get_settings()
    return SettingsResponse(
        env=settings.env,
        api_host=settings.api_host,
        api_port=settings.api_port,
        database_url=settings.database_url,
        log_level=settings.log_level,
        log_retention_days=settings.log_retention_days,
        metrics_retention_days=settings.metrics_retention_days,
        uvicorn_workers=settings.uvicorn_workers,
        worker_concurrency=settings.worker_concurrency,
        ssh_connect_timeout_seconds=settings.ssh_connect_timeout_seconds,
        ssh_command_timeout_seconds=settings.ssh_command_timeout_seconds,
    )


@router.post("", response_model=SettingsResponse)
def update_settings(user: CurrentUser, updates: SettingsUpdateRequest) -> SettingsResponse:
    """Update application settings in local .env and reload them."""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not update_dict:
        return get_current_settings(user)

    # Perform validation before writing to .env
    current = get_settings()

    # Construct dict of test fields
    test_fields = {
        "master_key": current.master_key,
        "session_secret": current.session_secret,
    }
    # Overlay current fields
    for field in current.model_fields:
        if field not in ["master_key", "session_secret"]:
            test_fields[field] = getattr(current, field)
    # Overlay the new updates
    test_fields.update(update_dict)

    try:
        # Validate using Settings model
        Settings(**test_fields)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration value: {str(e)}",
        )

    # Update .env and reload env vars
    update_dotenv(update_dict)

    # Return new settings
    return get_current_settings(user)
