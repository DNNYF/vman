"""add jobs, job_steps, job_logs (Milestone 3 / Task 11)

Revision ID: 20260105_0001
Revises: 20260104_0001
Create Date: 2026-01-05 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260105_0001"
down_revision = "20260104_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("host_id", sa.String(length=64), nullable=True),
        sa.Column("recipe_name", sa.String(length=128), nullable=True),
        sa.Column("command_summary", sa.String(length=2048), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column(
            "approval_status",
            sa.String(length=16),
            nullable=False,
            server_default="not_required",
        ),
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_summary_redacted", sa.String(length=2048), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
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
            "status IN ('queued', 'running', 'success', 'failed', 'cancelled', 'denied')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "approval_status IN ('not_required', 'pending', 'approved', 'denied')",
            name="ck_jobs_approval_status",
        ),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_host_id", "jobs", ["host_id"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "job_steps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_summary_redacted", sa.String(length=2048), nullable=True),
        sa.UniqueConstraint("job_id", "step_index", name="uq_job_steps_index"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'failed', 'cancelled', 'skipped')",
            name="ck_job_steps_status",
        ),
    )

    op.create_table(
        "job_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.String(length=64),
            sa.ForeignKey("job_steps.id"),
            nullable=True,
        ),
        sa.Column("stream", sa.String(length=16), nullable=False),
        sa.Column("line_redacted", sa.String(length=4096), nullable=False),
        sa.Column("line_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "stream IN ('stdout', 'stderr', 'system')",
            name="ck_job_logs_stream",
        ),
    )
    op.create_index("ix_job_logs_job_id", "job_logs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_logs_job_id", table_name="job_logs")
    op.drop_table("job_logs")
    op.drop_table("job_steps")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_host_id", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
