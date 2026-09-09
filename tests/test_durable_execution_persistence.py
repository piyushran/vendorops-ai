from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.authorization import ApprovalGrant, AuthorizationRequest, Policy, PolicyGate
from app.agent.durable_execution import DurableExecutionEngine
from app.agent.models import AgentRun, ToolExecution, ToolExecutionStatus
from app.agent.tool_registry import RiskClass, ScopeLevel, SideEffectClass, ToolDefinition
from app.db.base import Base


class InvoiceInput(BaseModel):
    vendor_id: str
    amount: float
    currency: str


class InvoiceOutput(BaseModel):
    external_id: str
    status: str
    amount: float


class FakeAdapter:
    def __init__(self, external_exists: bool = False) -> None:
        self.execute_calls = 0
        self.external_exists = external_exists

    def execute(self, tool: ToolDefinition, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        self.execute_calls += 1
        return {"external_id": f"invoice-{idempotency_key}", "status": "created", "amount": payload["amount"]}

    def verify(self, tool: ToolDefinition, payload: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        return {"verified": True, "external_id": output["external_id"]}

    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        return {"name": f"invoice-{idempotency_key}"} if self.external_exists else None


def request_and_approval() -> tuple[AuthorizationRequest, ApprovalGrant]:
    tool = ToolDefinition(
        name="create_vendor_invoice", version="1.0", description="Create a vendor invoice.",
        input_schema=InvoiceInput, output_schema=InvoiceOutput, side_effect=SideEffectClass.WRITE,
        risk=RiskClass.HIGH, required_capabilities=frozenset({"ap.invoice.write"}),
        scope_level=ScopeLevel.RESOURCE, resource_type="vendor_invoice",
    )
    request = AuthorizationRequest(
        organization_id="org-1", workspace_id="ws-1", actor_id="user-1", action=tool.name,
        tool=tool, input_payload={"vendor_id": "vendor-1", "amount": 100.0, "currency": "INR"},
        capabilities=frozenset({"ap.invoice.write"}), resource_id="invoice-1",
    )
    approval = ApprovalGrant(
        approval_id="approval-1", organization_id="org-1", workspace_id="ws-1", approved_by="approver",
        action_fingerprint=request.action_fingerprint, approved_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    return request, approval


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
async def test_persists_one_run_and_one_tool_execution(session: AsyncSession) -> None:
    request, approval = request_and_approval()
    policy = Policy(allowed_capabilities=frozenset({"ap.invoice.write"}), max_risk=RiskClass.HIGH, writable_actions=frozenset({request.action}))
    adapter = FakeAdapter()
    engine = DurableExecutionEngine(session, PolicyGate(policy))

    first = await engine.execute(request, approval=approval, adapter=adapter, idempotency_key="durable-1", case_id="case-1")
    second = await engine.execute(request, approval=approval, adapter=adapter, idempotency_key="durable-1", case_id="case-1")

    assert first.status.value == "succeeded"
    assert second.status == first.status
    assert adapter.execute_calls == 1
    assert await session.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert await session.scalar(select(func.count()).select_from(ToolExecution)) == 1


@pytest.mark.asyncio
async def test_expired_execution_reconciles_without_replaying_external_write(session: AsyncSession) -> None:
    request, _ = request_and_approval()
    policy = Policy(allowed_capabilities=frozenset({"ap.invoice.write"}), max_risk=RiskClass.HIGH, writable_actions=frozenset({request.action}))
    expired = datetime.now(UTC) - timedelta(seconds=1)
    run = AgentRun(
        organization_id="org-1", workspace_id="ws-1", case_id="case-1", requested_action=request.action,
        idempotency_key="crash-1", input_payload=request.input_payload, status=AgentRunStatus.EXECUTING.value,
        attempt=1, lease_owner="dead-worker", lease_expires_at=expired,
    )
    session.add(run)
    await session.flush()
    session.add(ToolExecution(
        agent_run_id=run.id, organization_id="org-1", workspace_id="ws-1", tool_name=request.action,
        status=ToolExecutionStatus.RUNNING.value, permission_scope="ap.invoice.write", idempotency_key="crash-1",
        input_payload=request.input_payload, lease_owner="dead-worker", lease_expires_at=expired,
    ))
    await session.commit()

    adapter = FakeAdapter(external_exists=True)
    recovered = await DurableExecutionEngine(session, PolicyGate(policy)).recover_expired(adapter)

    assert recovered == 1
    assert adapter.execute_calls == 0
    refreshed = await session.scalar(select(ToolExecution).where(ToolExecution.idempotency_key == "crash-1"))
    assert refreshed is not None
    assert refreshed.status == ToolExecutionStatus.SUCCEEDED.value
