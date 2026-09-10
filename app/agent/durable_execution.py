"""Database-backed governed execution with worker leases and crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.authorization import ApprovalGrant, AuthorizationRequest, PolicyGate
from app.agent.execution import ExecutionAdapter, ExecutionReceipt, ExecutionStatus
from app.agent.models import AgentRun, AgentRunStatus, ToolExecution, ToolExecutionStatus


class DurableExecutionError(RuntimeError):
    """Raised when durable execution cannot safely claim or reconcile work."""


class DurableExecutionEngine:
    """Persist the execution lifecycle before touching an external side effect."""

    def __init__(self, session: AsyncSession, policy_gate: PolicyGate, *, lease_seconds: int = 60) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")
        self.session = session
        self.policy_gate = policy_gate
        self.lease_seconds = lease_seconds

    async def execute(
        self,
        request: AuthorizationRequest,
        *,
        approval: ApprovalGrant | None,
        adapter: ExecutionAdapter,
        idempotency_key: str,
        case_id: str,
        permission_scope: str = "agent.execute",
        worker_id: str | None = None,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> ExecutionReceipt:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not case_id.strip():
            raise ValueError("case_id must not be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        current = now or datetime.now(UTC)
        existing = await self.session.scalar(
            select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
        )
        if existing:
            self._assert_same_request(existing, request, case_id)
            if existing.status in {
                AgentRunStatus.COMPLETED.value,
                AgentRunStatus.FAILED.value,
                AgentRunStatus.CANCELLED.value,
                AgentRunStatus.NEEDS_RECONCILIATION.value,
            }:
                return self._receipt_from_run(existing)

        decision = self.policy_gate.authorize(request, approval=approval, now=current)
        if not decision.allowed:
            run = await self._get_or_create_run(request, case_id, idempotency_key, current)
            self._assert_same_request(run, request, case_id)
            run.status = AgentRunStatus.CANCELLED.value
            run.error_message = decision.reason
            run.completed_at = current
            await self.session.commit()
            return self._receipt_from_run(run, status=ExecutionStatus.REJECTED)

        run = await self._get_or_create_run(request, case_id, idempotency_key, current)
        self._assert_same_request(run, request, case_id)
        owner = worker_id or f"worker-{uuid4()}"
        if not await self._claim(run.id, owner, current):
            await self.session.rollback()
            run = await self.session.scalar(select(AgentRun).where(AgentRun.id == run.id))
            if run is None:
                raise DurableExecutionError("execution disappeared during claim")
            self._assert_same_request(run, request, case_id)
            return self._receipt_from_run(run)

        tool = await self.session.scalar(
            select(ToolExecution).where(ToolExecution.idempotency_key == idempotency_key)
        )
        if tool is None:
            tool = ToolExecution(
                agent_run_id=run.id,
                organization_id=request.organization_id,
                workspace_id=request.workspace_id,
                tool_name=request.tool.name,
                status=ToolExecutionStatus.RUNNING.value,
                permission_scope=permission_scope,
                idempotency_key=idempotency_key,
                input_payload=request.input_payload,
                lease_owner=owner,
                lease_expires_at=current + timedelta(seconds=self.lease_seconds),
            )
            self.session.add(tool)
        else:
            if tool.agent_run_id != run.id or tool.organization_id != request.organization_id or tool.workspace_id != request.workspace_id:
                raise DurableExecutionError("idempotency key is already bound to another execution")
            tool.status = ToolExecutionStatus.RUNNING.value
            tool.lease_owner = owner
            tool.lease_expires_at = current + timedelta(seconds=self.lease_seconds)
        run.status = AgentRunStatus.EXECUTING.value
        run.attempt += 1
        await self.session.commit()

        try:
            validated = request.tool.validate_input(request.input_payload)
            output = adapter.execute(request.tool, validated.model_dump(), idempotency_key=idempotency_key)
            request.tool.validate_output(output)
            tool.status = ToolExecutionStatus.VERIFYING.value
            run.status = AgentRunStatus.VERIFYING.value
            await self.session.commit()
            verification = adapter.verify(request.tool, validated.model_dump(), output)
            if not verification.get("verified", False):
                raise DurableExecutionError(
                    verification.get("reason", "external action could not be verified")
                )
            completed = datetime.now(UTC)
            tool.status = ToolExecutionStatus.SUCCEEDED.value
            tool.output_payload = {"result": output, "verification": verification}
            tool.completed_at = completed
            tool.lease_owner = None
            tool.lease_expires_at = None
            run.status = AgentRunStatus.COMPLETED.value
            run.result_payload = {"result": output, "verification": verification}
            run.completed_at = completed
            run.lease_owner = None
            run.lease_expires_at = None
            await self.session.commit()
            return self._receipt_from_run(run, attempts=run.attempt, output=run.result_payload)
        except Exception as exc:  # noqa: BLE001
            tool.error_message = str(exc)
            tool.status = ToolExecutionStatus.FAILED.value
            tool.completed_at = datetime.now(UTC)
            tool.lease_owner = None
            tool.lease_expires_at = None
            run.status = (
                AgentRunStatus.FAILED.value
                if run.attempt >= max_attempts
                else AgentRunStatus.QUEUED.value
            )
            run.error_message = str(exc)
            run.lease_owner = None
            run.lease_expires_at = None
            await self.session.commit()
            return self._receipt_from_run(run, attempts=run.attempt, error=str(exc))

    async def heartbeat(self, execution_id: str, worker_id: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        result = await self.session.execute(
            update(ToolExecution)
            .where(and_(ToolExecution.id == execution_id, ToolExecution.lease_owner == worker_id))
            .values(lease_expires_at=current + timedelta(seconds=self.lease_seconds))
        )
        await self.session.commit()
        return result.rowcount == 1

    async def recover_expired(self, adapter: ExecutionAdapter, *, now: datetime | None = None) -> int:
        """Reconcile expired work without replaying an ambiguous external write."""
        current = now or datetime.now(UTC)
        rows = (
            await self.session.scalars(
                select(ToolExecution).where(
                    and_(
                        ToolExecution.status.in_(
                            [ToolExecutionStatus.RUNNING.value, ToolExecutionStatus.VERIFYING.value]
                        ),
                        ToolExecution.lease_expires_at.is_not(None),
                        ToolExecution.lease_expires_at < current,
                    )
                )
            )
        ).all()
        recovered = 0
        for tool in rows:
            run = await self.session.scalar(select(AgentRun).where(AgentRun.id == tool.agent_run_id))
            if run is None:
                continue
            finder = getattr(adapter, "find_by_idempotency_key", None)
            if not callable(finder):
                self._mark_reconciliation_required(tool, run, "adapter cannot reconcile external outcome")
            else:
                try:
                    external = finder(tool.idempotency_key)
                except Exception as exc:  # noqa: BLE001 - reconciliation must fail closed.
                    self._mark_reconciliation_required(
                        tool, run, f"reconciliation lookup failed: {exc}"
                    )
                else:
                    if external:
                        tool.status = ToolExecutionStatus.SUCCEEDED.value
                        tool.output_payload = {"reconciled": True, "external": external}
                        tool.completed_at = current
                        run.status = AgentRunStatus.COMPLETED.value
                        run.result_payload = {"reconciled": True, "external": external}
                        run.completed_at = current
                        run.error_message = None
                        recovered += 1
                    else:
                        self._mark_reconciliation_required(
                            tool, run, "no matching external document found"
                        )
            tool.lease_owner = None
            tool.lease_expires_at = None
            run.lease_owner = None
            run.lease_expires_at = None
        await self.session.commit()
        return recovered

    async def _get_or_create_run(
        self, request: AuthorizationRequest, case_id: str, key: str, now: datetime
    ) -> AgentRun:
        run = await self.session.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
        if run:
            return run
        run = AgentRun(
            organization_id=request.organization_id,
            workspace_id=request.workspace_id,
            case_id=case_id,
            requested_action=request.action,
            actor_id=request.actor_id,
            tool_identity=request.tool.identity,
            action_fingerprint=request.action_fingerprint,
            idempotency_key=key,
            input_payload=request.input_payload,
            created_at=now,
            updated_at=now,
        )
        self.session.add(run)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
            if existing is None:
                raise
            return existing
        return run

    async def _claim(self, run_id: str, owner: str, now: datetime) -> bool:
        result = await self.session.execute(
            update(AgentRun)
            .where(
                and_(
                    AgentRun.id == run_id,
                    or_(
                        AgentRun.status.in_(
                            [AgentRunStatus.QUEUED.value, AgentRunStatus.WAITING_FOR_APPROVAL.value]
                        ),
                        and_(
                            AgentRun.lease_expires_at.is_not(None),
                            AgentRun.lease_expires_at < now,
                        ),
                    ),
                )
            )
            .values(
                lease_owner=owner,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                status=AgentRunStatus.EXECUTING.value,
                started_at=now,
            )
        )
        return result.rowcount == 1

    @staticmethod
    def _assert_same_request(run: AgentRun, request: AuthorizationRequest, case_id: str) -> None:
        if (
            run.organization_id != request.organization_id
            or run.workspace_id != request.workspace_id
            or run.case_id != case_id
            or run.requested_action != request.action
            or run.actor_id != request.actor_id
            or run.tool_identity != request.tool.identity
            or run.action_fingerprint != request.action_fingerprint
            or run.input_payload != request.input_payload
        ):
            raise DurableExecutionError(
                "idempotency key is already bound to a different tenant, actor, action, or payload"
            )

    @staticmethod
    def _mark_reconciliation_required(
        tool: ToolExecution, run: AgentRun, reason: str
    ) -> None:
        tool.status = ToolExecutionStatus.NEEDS_RECONCILIATION.value
        tool.error_message = reason
        run.status = AgentRunStatus.NEEDS_RECONCILIATION.value
        run.error_message = reason

    @staticmethod
    def _receipt_from_run(
        run: AgentRun,
        *,
        status: ExecutionStatus | None = None,
        attempts: int | None = None,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ExecutionReceipt:
        mapped = status or {
            AgentRunStatus.COMPLETED.value: ExecutionStatus.SUCCEEDED,
            AgentRunStatus.CANCELLED.value: ExecutionStatus.REJECTED,
            AgentRunStatus.FAILED.value: ExecutionStatus.FAILED,
            AgentRunStatus.NEEDS_RECONCILIATION.value: ExecutionStatus.NEEDS_RECONCILIATION,
            AgentRunStatus.EXECUTING.value: ExecutionStatus.EXECUTING,
            AgentRunStatus.VERIFYING.value: ExecutionStatus.VERIFYING,
        }.get(run.status, ExecutionStatus.REQUESTED)
        return ExecutionReceipt(
            execution_id=run.id,
            organization_id=run.organization_id,
            workspace_id=run.workspace_id,
            actor_id=run.actor_id,
            tool_identity=run.tool_identity,
            action_fingerprint=run.action_fingerprint,
            idempotency_key=run.idempotency_key,
            status=mapped,
            attempts=run.attempt if attempts is None else attempts,
            output=output if output is not None else run.result_payload,
            error=error if error is not None else run.error_message,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )
