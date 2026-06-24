"""Pydantic schemas for the credentials/vault API."""

from __future__ import annotations

import datetime
from pydantic import BaseModel, Field, field_validator


class CredentialCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., min_length=1, max_length=32)
    plaintext: str = Field(..., min_length=1)

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        valid_kinds = {
            "ssh_password",
            "ssh_private_key",
            "ssh_private_key_passphrase",
            "sudo_password",
            "api_token",
        }
        if v not in valid_kinds:
            raise ValueError(f"kind must be one of {valid_kinds}")
        return v


class CredentialOut(BaseModel):
    id: str
    name: str
    kind: str
    fingerprint: str
    metadata_json: dict
    last_used_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


__all__ = ["CredentialCreate", "CredentialOut"]
