"""Add durable job execution metadata.

Revision ID: 202608290001
Revises: 202604270001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202608290001"
down_revision: str | None = "202604270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
        )
        batch.add_column(sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("lease_owner", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("execution_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("execution_metadata", sa.JSON(), nullable=True))
    op.execute("UPDATE processing_jobs SET next_run_at = created_at WHERE next_run_at IS NULL")
    op.create_index(
        "idx_jobs_dispatch", "processing_jobs", ["status", "next_run_at", "lease_expires_at"]
    )
    op.create_index("ix_processing_jobs_lease_owner", "processing_jobs", ["lease_owner"])
    op.create_index("ix_processing_jobs_lease_expires_at", "processing_jobs", ["lease_expires_at"])
    op.create_index("ix_processing_jobs_execution_id", "processing_jobs", ["execution_id"])
    op.create_index("uq_records_job", "extracted_records", ["job_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_records_job", table_name="extracted_records")
    op.drop_index("ix_processing_jobs_execution_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_lease_expires_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_lease_owner", table_name="processing_jobs")
    op.drop_index("idx_jobs_dispatch", table_name="processing_jobs")
    with op.batch_alter_table("processing_jobs") as batch:
        for column in (
            "execution_metadata",
            "execution_id",
            "lease_expires_at",
            "lease_owner",
            "failed_at",
            "completed_at",
            "started_at",
            "next_run_at",
            "max_attempts",
            "attempts",
        ):
            batch.drop_column(column)
