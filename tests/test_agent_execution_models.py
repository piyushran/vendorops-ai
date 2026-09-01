from datetime import UTC, datetime

from app.agent.models import AgentRun, AgentRunStatus, ToolExecution, ToolExecutionStatus


def test_agent_run_defaults_support_durable_execution() -> None:
    run = AgentRun(
        organization_id="org-1",
        workspace_id="ws-1",
        case_id="case-1",
        requested_action="sync_vendor",
        idempotency_key="run-case-1-sync-vendor",
        input_payload={"vendor_id": "v-1"},
    )

    assert run.status == AgentRunStatus.QUEUED.value
    assert run.attempt == 0
    assert run.result_payload is None


def test_tool_execution_carries_tenant_scope_and_idempotency() -> None:
    execution = ToolExecution(
        agent_run_id="run-1",
        organization_id="org-1",
        workspace_id="ws-1",
        tool_name="vendor_api.update",
        permission_scope="vendor.write",
        idempotency_key="tool-run-1-update-vendor",
        input_payload={"vendor_id": "v-1"},
    )

    assert execution.status == ToolExecutionStatus.REQUESTED.value
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
