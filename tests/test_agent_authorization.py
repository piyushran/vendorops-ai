from datetime import UTC, datetime, timedelta

import pytest

from app.agent.authorization import (
    ApprovalGrant,
    AuthorizationDenied,
    AuthorizationRequest,
    Policy,
    PolicyGate,
)
from app.agent.tool_catalog import build_default_tool_registry


@pytest.fixture
def tools():
    return build_default_tool_registry()


def make_request(tools, *, action="vendor.lookup", payload=None, resource_id=None):
    tool = tools.get(*action.split("@")) if "@" in action else tools.get(action, "1.0")
    return AuthorizationRequest(
        organization_id="org-1",
        workspace_id="ws-1",
        actor_id="user-1",
        action=tool.name,
        tool=tool,
        input_payload=payload or {"vendor_id": "vendor-1"},
        capabilities=frozenset({"vendor.read", "vendor.write"}),
        resource_id=resource_id,
    )


def test_deny_by_default_for_write_without_explicit_policy(tools):
    request = make_request(tools, action="vendor.update", resource_id="vendor-1")
    gate = PolicyGate(
        Policy(
            allowed_capabilities=frozenset({"vendor.write"}),
            max_risk=request.tool.risk,
        )
    )

    decision = gate.authorize(request)

    assert decision.allowed is False
    assert "explicitly allowed" in decision.reason


def test_read_action_can_be_authorized_without_approval(tools):
    request = make_request(tools)
    gate = PolicyGate(
        Policy(
            allowed_capabilities=frozenset({"vendor.read"}),
        )
    )

    decision = gate.enforce(request)

    assert decision.allowed is True
    assert decision.reason == "authorized"


def test_write_requires_explicit_action_and_exact_approval(tools):
    request = make_request(tools, action="vendor.update", resource_id="vendor-1")
    gate = PolicyGate(
        Policy(
            allowed_capabilities=frozenset({"vendor.write"}),
            max_risk=request.tool.risk,
            writable_actions=frozenset({"vendor.update"}),
        )
    )
    approval = ApprovalGrant(
        approval_id="approval-1",
        organization_id="org-1",
        workspace_id="ws-1",
        approved_by="approver-1",
        action_fingerprint=request.action_fingerprint,
        approved_at=datetime.now(UTC),
    )

    decision = gate.enforce(request, approval=approval)

    assert decision.allowed is True
    assert decision.approval_id == "approval-1"


def test_approval_cannot_be_replayed_for_changed_payload(tools):
    request = make_request(tools, action="vendor.update", resource_id="vendor-1")
    gate = PolicyGate(
        Policy(
            allowed_capabilities=frozenset({"vendor.write"}),
            max_risk=request.tool.risk,
            writable_actions=frozenset({"vendor.update"}),
        )
    )
    approval = ApprovalGrant(
        approval_id="approval-1",
        organization_id="org-1",
        workspace_id="ws-1",
        approved_by="approver-1",
        action_fingerprint=request.action_fingerprint,
        approved_at=datetime.now(UTC),
    )
    changed = make_request(
        tools,
        action="vendor.update",
        payload={"vendor_id": "vendor-1", "status": "suspended"},
        resource_id="vendor-1",
    )

    decision = gate.authorize(changed, approval=approval)

    assert decision.allowed is False
    assert "exact action" in decision.reason


def test_approval_cannot_cross_workspace_or_expire(tools):
    request = make_request(tools, action="vendor.update", resource_id="vendor-1")
    gate = PolicyGate(
        Policy(
            allowed_capabilities=frozenset({"vendor.write"}),
            max_risk=request.tool.risk,
            writable_actions=frozenset({"vendor.update"}),
        )
    )
    approval = ApprovalGrant(
        approval_id="approval-1",
        organization_id="org-1",
        workspace_id="other-workspace",
        approved_by="approver-1",
        action_fingerprint=request.action_fingerprint,
        approved_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    assert gate.authorize(request, approval=approval).allowed is False

    expired = ApprovalGrant(
        approval_id="approval-2",
        organization_id="org-1",
        workspace_id="ws-1",
        approved_by="approver-1",
        action_fingerprint=request.action_fingerprint,
        approved_at=datetime.now(UTC) - timedelta(minutes=10),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert gate.authorize(request, approval=expired).allowed is False


def test_enforce_raises_for_denied_action(tools):
    request = make_request(tools, action="vendor.update", resource_id="vendor-1")

    with pytest.raises(AuthorizationDenied):
        PolicyGate().enforce(request)
