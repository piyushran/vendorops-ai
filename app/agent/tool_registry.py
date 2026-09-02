from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError


class SideEffectClass(StrEnum):
    READ = "read"
    WRITE = "write"


class RiskClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScopeLevel(StrEnum):
    TENANT = "tenant"
    WORKSPACE = "workspace"
    RESOURCE = "resource"


class ToolValidationError(ValueError):
    """Raised when a tool payload does not satisfy its declared schema."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effect: SideEffectClass
    risk: RiskClass
    required_capabilities: frozenset[str]
    scope_level: ScopeLevel
    resource_type: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.version.strip():
            raise ValueError("tool version must not be empty")
        if self.scope_level is ScopeLevel.RESOURCE and not self.resource_type:
            raise ValueError("resource-scoped tools must declare resource_type")
        if self.scope_level is not ScopeLevel.RESOURCE and self.resource_type is not None:
            raise ValueError("resource_type is only valid for resource-scoped tools")

    @property
    def identity(self) -> str:
        return f"{self.name}@{self.version}"

    def validate_input(self, payload: dict[str, Any]) -> BaseModel:
        try:
            return self.input_schema.model_validate(payload)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc

    def validate_output(self, payload: dict[str, Any]) -> BaseModel:
        try:
            return self.output_schema.model_validate(payload)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc


class ToolRegistry:
    """Deterministic registry for agent-visible tool capabilities."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.identity in self._tools:
            raise ValueError(f"tool already registered: {tool.identity}")
        self._tools[tool.identity] = tool

    def get(self, name: str, version: str) -> ToolDefinition:
        identity = f"{name}@{version}"
        try:
            return self._tools[identity]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {identity}") from exc

    def discover(
        self,
        *,
        capabilities: set[str] | frozenset[str],
        include_side_effects: set[SideEffectClass] | frozenset[SideEffectClass] | None = None,
        max_risk: RiskClass | None = None,
    ) -> tuple[ToolDefinition, ...]:
        allowed_side_effects = include_side_effects or frozenset(SideEffectClass)
        risk_rank = {
            RiskClass.LOW: 0,
            RiskClass.MEDIUM: 1,
            RiskClass.HIGH: 2,
            RiskClass.CRITICAL: 3,
        }
        max_risk_rank = risk_rank[max_risk] if max_risk is not None else risk_rank[RiskClass.CRITICAL]

        visible = [
            tool
            for tool in self._tools.values()
            if tool.required_capabilities.issubset(capabilities)
            and tool.side_effect in allowed_side_effects
            and risk_rank[tool.risk] <= max_risk_rank
        ]
        return tuple(sorted(visible, key=lambda tool: tool.identity))

    def all(self) -> tuple[ToolDefinition, ...]:
        return tuple(sorted(self._tools.values(), key=lambda tool: tool.identity))
