from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.agent.tool_registry import RiskClass, SideEffectClass, ToolDefinition


class AuthorizationDenied(PermissionError):
    """Raised when an agent action fails the authorization policy gate."""


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    organization_id: str
    workspace_id: str
    actor_id: str
    action: str
    tool: ToolDefinition
    input_payload: dict[str, Any]
    capabilities: frozenset[str]
    resource_id: str | None = None

    @property
    def action_fingerprint(self) -> str:
        canonical = {
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "tool": self.tool.identity,
            "input_payload": self.input_payload,
            "resource_id": self.resource_id,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    approval_id: str
    organization_id: str
    workspace_id: str
    approved_by: str
    action_fingerprint: str
    approved_at: datetime
    expires_at: datetime | None = None

    def is_valid_for(self, request: AuthorizationRequest, now: datetime) -> bool:
        if self.organization_id != request.organization_id:
            return False
        if self.workspace_id != request.workspace_id:
            return False
        if self.action_fingerprint != request.action_fingerprint:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Policy:
    """Explicit allow policy; everything not described here is denied."""

    allowed_capabilities: frozenset[str] = frozenset()
    max_risk: RiskClass = RiskClass.LOW
    writable_actions: frozenset[str] = frozenset()
    require_approval_for_writes: bool = True
    allowed_resource_ids: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    action_fingerprint: str
    approval_id: str | None = None


class PolicyGate:
    """Deny-by-default authorization gate evaluated immediately before execution."""

    _risk_rank = {
        RiskClass.LOW: 0,
        RiskClass.MEDIUM: 1,
        RiskClass.HIGH: 2,
        RiskClass.CRITICAL: 3,
    }

    def __init__(self, policy: Policy | None = None) -> None:
        self.policy = policy or Policy()

    def authorize(
        self,
        request: AuthorizationRequest,
        *,
        approval: ApprovalGrant | None = None,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        fingerprint = request.action_fingerprint
        current_time = now or datetime.now(UTC)

        if request.action != request.tool.name:
            return self._deny(request, "authorization action must match the registered tool name")

        if request.tool.required_capabilities - self.policy.allowed_capabilities:
            return self._deny(request, "required capability is not allowed by policy")

        if request.tool.required_capabilities - request.capabilities:
            return self._deny(request, "actor is missing a required capability")

        if self._risk_rank[request.tool.risk] > self._risk_rank[self.policy.max_risk]:
            return self._deny(request, "tool risk exceeds policy maximum")

        if request.tool.scope_level.value == "resource":
            if not request.resource_id:
                return self._deny(request, "resource-scoped action requires resource_id")
            if (
                self.policy.allowed_resource_ids is not None
                and request.resource_id not in self.policy.allowed_resource_ids
            ):
                return self._deny(request, "resource is outside the allowed policy scope")

        if request.tool.side_effect is SideEffectClass.WRITE:
            if request.action not in self.policy.writable_actions:
                return self._deny(request, "write action is not explicitly allowed")
            if self.policy.require_approval_for_writes:
                if approval is None or not approval.is_valid_for(request, current_time):
                    return self._deny(request, "valid approval for the exact action is required")

        return AuthorizationDecision(
            allowed=True,
            reason="authorized",
            action_fingerprint=fingerprint,
            approval_id=approval.approval_id if approval else None,
        )

    def enforce(
        self,
        request: AuthorizationRequest,
        *,
        approval: ApprovalGrant | None = None,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        decision = self.authorize(request, approval=approval, now=now)
        if not decision.allowed:
            raise AuthorizationDenied(decision.reason)
        return decision

    @staticmethod
    def _deny(request: AuthorizationRequest, reason: str) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=False,
            reason=reason,
            action_fingerprint=request.action_fingerprint,
        )
