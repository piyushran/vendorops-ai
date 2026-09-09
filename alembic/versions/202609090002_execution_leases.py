"""Add durable worker lease and reconciliation state to executions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202609090002"
down_revision: str | None = "202609010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_lease_owner", "agent_runs", ["lease_owner"])
    op.create_index("ix_agent_runs_lease_expires_at", "agent_runs", ["lease_expires_at"])

    op.add_column("tool_executions", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    op.add_column("tool_executions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tool_executions_lease_owner", "tool_executions", ["lease_owner"])
    op.create_index("ix_tool_executions_lease_expires_at", "tool_executions", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_executions_lease_expires_at", table_name="tool_executions")
    op.drop_index("ix_tool_executions_lease_owner", table_name="tool_executions")
    op.drop_column("tool_executions", "lease_expires_at")
    op.drop_column("tool_executions", "lease_owner")
    op.drop_index("ix_agent_runs_lease_expires_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_lease_owner", table_name="agent_runs")
    op.drop_column("agent_runs", "lease_expires_at")
    op.drop_column("agent_runs", "lease_owner")
