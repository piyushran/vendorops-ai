"""Controlled execution engine for approved agent tool actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.agent.authorization import ApprovalGrant, AuthorizationRequest, PolicyGate
from app.agent.tool_registry import ToolDefinition, ToolValidationError


class ExecutionStatus(StrEnum):
    REQUESTED = "requested"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    execution_id: str
    organization_id: str
    workspace_id: str
    actor_id: str
    tool_identity: str
    action_fingerprint: str
    idempotency_key: str
    status: ExecutionStatus
    attempts: int
    output: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    output: dict[str, Any]
    verification: dict[str, Any] = field(default_factory=dict)


class ExecutionAdapter(Protocol):
    """External side-effect adapter implemented by AP/ERP connectors."""

    def execute(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    def verify(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]: ...


class ExecutionError(RuntimeError):
    """Raised when an approved execution cannot complete safely."""


@dataclass
class _ExecutionRecord:
    receipt: ExecutionReceipt
    result: ExecutionResult | None = None


class ExecutionEngine:
    """Execute approved tool actions with deterministic idempotency and verification.

    The engine deliberately owns no external credentials. Connectors are injected as
    adapters, keeping real side effects behind the same authorization boundary.
    """

    def __init__(self, policy_gate: PolicyGate) -> None:
        self.policy_gate = policy_gate
        self._executions: dict[str, _ExecutionRecord] = {}
        self._receipts_by_idempotency: dict[str, ExecutionReceipt] = {}

    def execute(
        self,
        request: AuthorizationRequest,
        *,
        approval: ApprovalGrant | None,
        adapter: ExecutionAdapter,
        idempotency_key: str,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> ExecutionReceipt:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        existing = self._receipts_by_idempotency.get(idempotency_key)
        if existing is not None:
            return existing

        current_time = now or datetime.now(UTC)
        decision = self.policy_gate.authorize(
            request,
            approval=approval,
            now=current_time,
        )
        if not decision.allowed:
            receipt = self._receipt(
                request,
                idempotency_key=idempotency_key,
                status=ExecutionStatus.REJECTED,
                attempts=0,
                error=decision.reason,
                created_at=current_time,
            )
            self._store(receipt)
            return receipt

        try:
            validated_input = request.tool.validate_input(request.input_payload)
        except ToolValidationError as exc:
            receipt = self._receipt(
                request,
                idempotency_key=idempotency_key,
                status=ExecutionStatus.FAILED,
                attempts=0,
                error=str(exc),
                created_at=current_time,
            )
            self._store(receipt)
            return receipt

        last_error: str | None = None
        attempts = 0
        output: dict[str, Any] | None = None
        for attempts in range(1, max_attempts + 1):
            try:
                output = adapter.execute(
                    request.tool,
                    validated_input.model_dump(),
                    idempotency_key=idempotency_key,
                )
                request.tool.validate_output(output)
                verification = adapter.verify(
                    request.tool,
                    validated_input.model_dump(),
                    output,
                )
                if not verification.get("verified", False):
                    raise ExecutionError(
                        verification.get("reason", "external action could not be verified")
                    )
                completed = datetime.now(UTC)
                result = ExecutionResult(output=output, verification=verification)
                receipt = self._receipt(
                    request,
                    idempotency_key=idempotency_key,
                    status=ExecutionStatus.SUCCEEDED,
                    attempts=attempts,
                    output={"result": result.output, "verification": result.verification},
                    created_at=current_time,
                    completed_at=completed,
                )
                self._store(receipt, result)
                return receipt
            except Exception as exc:  # noqa: BLE001 - adapter failures are recoverable.
                last_error = str(exc)

        receipt = self._receipt(
            request,
            idempotency_key=idempotency_key,
            status=ExecutionStatus.FAILED,
            attempts=attempts,
            output=output,
            error=last_error,
            created_at=current_time,
            completed_at=datetime.now(UTC),
        )
        self._store(receipt)
        return receipt

    def get_receipt(self, idempotency_key: str) -> ExecutionReceipt | None:
        return self._receipts_by_idempotency.get(idempotency_key)

    def _store(self, receipt: ExecutionReceipt, result: ExecutionResult | None = None) -> None:
        self._receipts_by_idempotency[receipt.idempotency_key] = receipt
        self._executions[receipt.execution_id] = _ExecutionRecord(receipt=receipt, result=result)

    @staticmethod
    def _receipt(
        request: AuthorizationRequest,
        *,
        idempotency_key: str,
        status: ExecutionStatus,
        attempts: int,
        error: str | None = None,
        output: dict[str, Any] | None = None,
        created_at: datetime,
        completed_at: datetime | None = None,
    ) -> ExecutionReceipt:
        from uuid import uuid4

        return ExecutionReceipt(
            execution_id=str(uuid4()),
            organization_id=request.organization_id,
            workspace_id=request.workspace_id,
            actor_id=request.actor_id,
            tool_identity=request.tool.identity,
            action_fingerprint=request.action_fingerprint,
            idempotency_key=idempotency_key,
            status=status,
            attempts=attempts,
            output=output,
            error=error,
            created_at=created_at,
            completed_at=completed_at,
        )
