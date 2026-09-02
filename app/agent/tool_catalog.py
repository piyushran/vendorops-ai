from pydantic import BaseModel

from app.agent.tool_registry import (
    RiskClass,
    ScopeLevel,
    SideEffectClass,
    ToolDefinition,
    ToolRegistry,
)


class VendorLookupInput(BaseModel):
    vendor_id: str


class VendorLookupOutput(BaseModel):
    vendor_id: str
    status: str


class VendorUpdateInput(BaseModel):
    vendor_id: str
    status: str


class VendorUpdateOutput(BaseModel):
    updated: bool


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="vendor.lookup",
            version="1.0",
            description="Read vendor status from an approved vendor system adapter",
            input_schema=VendorLookupInput,
            output_schema=VendorLookupOutput,
            side_effect=SideEffectClass.READ,
            risk=RiskClass.LOW,
            required_capabilities=frozenset({"vendor.read"}),
            scope_level=ScopeLevel.WORKSPACE,
        )
    )
    registry.register(
        ToolDefinition(
            name="vendor.update",
            version="1.0",
            description="Update vendor status through an approved vendor system adapter",
            input_schema=VendorUpdateInput,
            output_schema=VendorUpdateOutput,
            side_effect=SideEffectClass.WRITE,
            risk=RiskClass.HIGH,
            required_capabilities=frozenset({"vendor.write"}),
            scope_level=ScopeLevel.RESOURCE,
            resource_type="vendor",
        )
    )
    return registry
