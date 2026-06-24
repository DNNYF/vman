"""add audit hash chain fields

Revision ID: 20260106_0001
Revises: 20260105_0001
Create Date: 2026-01-06 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260106_0001"
down_revision = "20260105_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("previous_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "audit_events",
        sa.Column("event_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_hash", table_name="audit_events")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
