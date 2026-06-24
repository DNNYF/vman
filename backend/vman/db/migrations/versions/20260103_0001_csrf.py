"""add csrf_token_hash to sessions (Milestone 1 / Task 6)

Revision ID: 20260103_0001
Revises: 20260102_0001
Create Date: 2026-01-03 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260103_0001"
down_revision = "20260102_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "csrf_token_hash",
            sa.String(length=128),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "csrf_token_hash")
