"""add hosts table (Milestone 2 / Task 8)

Revision ID: 20260104_0001
Revises: 20260103_0001
Create Date: 2026-01-04 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260104_0001"
down_revision = "20260103_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("hostname_or_ip", sa.String(length=255), nullable=False),
        sa.Column(
            "ssh_port",
            sa.Integer(),
            nullable=False,
            server_default="22",
        ),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("auth_method", sa.String(length=32), nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=True),
        sa.Column(
            "sudo_mode",
            sa.String(length=32),
            nullable=False,
            server_default="root",
        ),
        sa.Column("host_key_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("host_key_algorithm", sa.String(length=16), nullable=True),
        sa.Column("os_family", sa.String(length=32), nullable=True),
        sa.Column("os_name", sa.String(length=64), nullable=True),
        sa.Column("os_version", sa.String(length=64), nullable=True),
        sa.Column("package_manager", sa.String(length=32), nullable=True),
        sa.Column("arch", sa.String(length=16), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("ram_mb", sa.Integer(), nullable=True),
        sa.Column("disk_total_mb", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column(
            "environment",
            sa.String(length=16),
            nullable=False,
            server_default="experiment",
        ),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "notes",
            sa.String(length=2048),
            nullable=False,
            server_default="",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "auth_method IN ('password', 'key', 'key_with_passphrase')",
            name="ck_hosts_auth_method",
        ),
        sa.CheckConstraint(
            "sudo_mode IN ('root', 'passwordless_sudo', 'sudo_password')",
            name="ck_hosts_sudo_mode",
        ),
        sa.CheckConstraint(
            "environment IN ('experiment', 'staging', 'production')",
            name="ck_hosts_environment",
        ),
    )
    op.create_index("ix_hosts_tags", "hosts", ["tags"])
    op.create_index("ix_hosts_environment", "hosts", ["environment"])


def downgrade() -> None:
    op.drop_index("ix_hosts_environment", table_name="hosts")
    op.drop_index("ix_hosts_tags", table_name="hosts")
    op.drop_table("hosts")
