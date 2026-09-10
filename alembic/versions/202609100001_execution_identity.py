"""Persist actor, tool and action identity for durable execution receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202609100001"
down_revision: str | Sequence[str] | None = "202609090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("actor_id", sa.String(length=255), nullable=True))
    op.add_column("agent_runs", sa.Column("tool_identity", sa.String(length=255), nullable=True))
    op.add_column("agent_runs", sa.Column("action_fingerprint", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE agent_runs SET actor_id = 'unknown' WHERE actor_id IS NULL"))
    bind.execute(sa.text("UPDATE agent_runs SET tool_identity = requested_action WHERE tool_identity IS NULL"))
    bind.execute(sa.text("UPDATE agent_runs SET action_fingerprint = 'legacy' WHERE action_fingerprint IS NULL"))

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.alter_column("actor_id", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("tool_identity", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("action_fingerprint", existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    op.drop_column("agent_runs", "action_fingerprint")
    op.drop_column("agent_runs", "tool_identity")
    op.drop_column("agent_runs", "actor_id")
