from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from app.agent.authorization import ApprovalGrant, AuthorizationRequest, Policy, PolicyGate
from app.agent.execution import ExecutionEngine, ExecutionStatus
from app.agent.tool_registry import RiskClass, ScopeLevel, SideEffectClass, ToolDefinition


class InvoiceInput(BaseModel):
    vendor_id: str
    amount: float
    currency: str


class InvoiceOutput(BaseModel):
    external_id: str
    status: str
    amount: float


class FakeAdapter:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.execute_calls = 0
        self.verify_calls = 0

    def execute(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.execute_calls += 1
        if self.execute_calls <= self.failures:
            raise RuntimeError("temporary adapter failure")
        return {
            "external_id": f"invoice-{idempotency_key}",
            "status": "created",
            "amount": payload["amount"],
        }

    def verify(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        self.verify_calls += 1
        return {
            "verified": output["status"] == "created"
            and output["amount"] == payload["amount"],
            "external_id": output["external_id"],
        }


def invoice_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_vendor_invoice",
        version="1.0",
        description="Create an approved vendor invoice in an external AP system.",
        input_schema=InvoiceInput,
        output_schema=InvoiceOutput,
        side_effect=SideEffectClass.WRITE,
        risk=RiskClass.HIGH,
        required_capabilities=frozenset({"ap.invoice.write"}),
        scope_level=ScopeLevel.RESOURCE,
        resource_type="vendor_invoice",
    )


def authorized_request() -> tuple[AuthorizationRequest, ApprovalGrant]:
    tool = invoice_tool()
    request = AuthorizationRequest(
        organization_id="org-1",
        workspace_id="ws-1",
        actor_id="user-1",
        action=tool.name,
        tool=tool,
        input_payload={"vendor_id": "vendor-7", "amount": 1250.0, "currency": "INR"},
        capabilities=frozenset({"ap.invoice.write"}),
        resource_id="invoice-1",
    )
    approval = ApprovalGrant(
        approval_id="approval-1",
        organization_id="org-1",
        workspace_id="ws-1",
        approved_by="approver-1",
        action_fingerprint=request.action_fingerprint,
        approved_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    return request, approval


def test_successful_execution_is_verified_and_receipted() -> None:
    request, approval = authorized_request()
    policy = Policy(
        allowed_capabilities=frozenset({"ap.invoice.write"}),
        max_risk=RiskClass.HIGH,
        writable_actions=frozenset({request.action}),
    )
    adapter = FakeAdapter()
    receipt = ExecutionEngine(PolicyGate(policy)).execute(
        request,
        approval=approval,
        adapter=adapter,
        idempotency_key="invoice-write-1",
    )

    assert receipt.status is ExecutionStatus.SUCCEEDED
    assert receipt.attempts == 1
    assert receipt.output is not None
    assert receipt.output["verification"]["verified"] is True
    assert adapter.execute_calls == 1
    assert adapter.verify_calls == 1


def test_idempotency_returns_original_receipt_without_second_side_effect() -> None:
    request, approval = authorized_request()
    policy = Policy(
        allowed_capabilities=frozenset({"ap.invoice.write"}),
        max_risk=RiskClass.HIGH,
        writable_actions=frozenset({request.action}),
    )
    adapter = FakeAdapter()
    engine = ExecutionEngine(PolicyGate(policy))

    first = engine.execute(
        request, approval=approval, adapter=adapter, idempotency_key="invoice-write-2"
    )
    second = engine.execute(
        request, approval=approval, adapter=adapter, idempotency_key="invoice-write-2"
    )

    assert second == first
    assert adapter.execute_calls == 1
    assert adapter.verify_calls == 1


def test_missing_approval_never_calls_adapter() -> None:
    request, _ = authorized_request()
    policy = Policy(
        allowed_capabilities=frozenset({"ap.invoice.write"}),
        max_risk=RiskClass.HIGH,
        writable_actions=frozenset({request.action}),
    )
    adapter = FakeAdapter()
    receipt = ExecutionEngine(PolicyGate(policy)).execute(
        request,
        approval=None,
        adapter=adapter,
        idempotency_key="invoice-write-3",
    )

    assert receipt.status is ExecutionStatus.REJECTED
    assert adapter.execute_calls == 0


def test_transient_failures_are_retried_and_can_succeed() -> None:
    request, approval = authorized_request()
    policy = Policy(
        allowed_capabilities=frozenset({"ap.invoice.write"}),
        max_risk=RiskClass.HIGH,
        writable_actions=frozenset({request.action}),
    )
    adapter = FakeAdapter(failures=2)
    receipt = ExecutionEngine(PolicyGate(policy)).execute(
        request,
        approval=approval,
        adapter=adapter,
        idempotency_key="invoice-write-4",
        max_attempts=3,
    )

    assert receipt.status is ExecutionStatus.SUCCEEDED
    assert receipt.attempts == 3
    assert adapter.execute_calls == 3
    assert adapter.verify_calls == 1
