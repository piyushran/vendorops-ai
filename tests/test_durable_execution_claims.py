from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.durable_execution import DurableExecutionEngine
from app.agent.models import AgentRun, AgentRunStatus
from app.db.base import Base


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed(session: AsyncSession) -> None:
    run = AgentRun(
        organization_id="org", workspace_id="ws", case_id="case", requested_action="tool",
        idempotency_key="claim-1", input_payload={}, status=AgentRunStatus.EXECUTING.value,
        lease_owner="dead", lease_expires_at=datetime.now(UTC) - timedelta(seconds=1), attempt=1,
    )
    session.add(run)
    await session.commit()

    engine = DurableExecutionEngine(session, object(), lease_seconds=30)
    assert await engine._claim(run.id, "new-worker", datetime.now(UTC)) is True
    refreshed = await session.scalar(select(AgentRun).where(AgentRun.id == run.id))
    assert refreshed is not None
    assert refreshed.lease_owner == "new-worker"
