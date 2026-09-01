from datetime import UTC, datetime

from app.agent.models import AgentRun, AgentRunStatus, ToolExecution, ToolExecutionStatus


def test_agent_run_defaults_support_durable_execution() -> None:
    status_default = AgentRun.__table__.c.status.default
    attempt_default = AgentRun.__table__.c.attempt.default

    assert status_default is not None
    assert attempt_default is not None
    assert status_default.arg == AgentRunStatus.QUEUED.value
    assert attempt_default.arg == 0

    run = AgentRun(
        organization_id="org-1",
        workspace_id="ws-1",
        case_id="case-1",
        requested_action="sync_vendor",
        idempotency_key="run-case-1-sync-vendor",
        input_payload={"vendor_id": "v-1"},
    )

    assert run.result_payload is None


def test_tool_execution_carries_tenant_scope_and_idempotency() -> None:
    status_default = ToolExecution.__table__.c.status.default

    assert status_default is not None
    assert status_default.arg == ToolExecutionStatus.REQUESTED.value

    execution = ToolExecution(
        agent_run_id="run-1",
        organization_id="org-1",
        workspace_id="ws-1",
        tool_name="vendor_api.update",
        permission_scope="vendor.write",
        idempotency_key="tool-run-1-update-vendor",
        input_payload={"vendor_id": "v-1"},
    )

    assert execution.permission_scope == "vendor.write"
    assert execution.idempotency_key == "tool-run-1-update-vendor"


def test_agent_run_timestamps_accept_aware_datetimes() -> None:
    timestamp = datetime.now(UTC)
    run = AgentRun(
        organization_id="org-1",
        workspace_id="ws-1",
        case_id="case-1",
        requested_action="sync_vendor",
        idempotency_key="run-case-1-sync-vendor-2",
        input_payload={},
        started_at=timestamp,
    )

    assert run.started_at == timestamp
