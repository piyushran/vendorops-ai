from pydantic import BaseModel

from app.agent.tool_registry import (
    RiskClass,
    ScopeLevel,
    SideEffectClass,
    ToolDefinition,
    ToolRegistry,
    ToolValidationError,
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


def _lookup_tool() -> ToolDefinition:
    return ToolDefinition(
        name="vendor.lookup",
        version="1.0",
        description="Read vendor status",
        input_schema=VendorLookupInput,
        output_schema=VendorLookupOutput,
        side_effect=SideEffectClass.READ,
        risk=RiskClass.LOW,
        required_capabilities=frozenset({"vendor.read"}),
        scope_level=ScopeLevel.WORKSPACE,
    )


def _update_tool() -> ToolDefinition:
    return ToolDefinition(
        name="vendor.update",
        version="1.0",
        description="Update vendor status",
        input_schema=VendorUpdateInput,
        output_schema=VendorUpdateOutput,
        side_effect=SideEffectClass.WRITE,
        risk=RiskClass.HIGH,
        required_capabilities=frozenset({"vendor.write"}),
        scope_level=ScopeLevel.RESOURCE,
        resource_type="vendor",
    )


def test_registry_tracks_versioned_tool_identity() -> None:
    registry = ToolRegistry()
    tool = _lookup_tool()
    registry.register(tool)

    assert tool.identity == "vendor.lookup@1.0"
    assert registry.get("vendor.lookup", "1.0") is tool


def test_registry_rejects_duplicate_identity() -> None:
    registry = ToolRegistry()
    tool = _lookup_tool()
    registry.register(tool)

    try:
        registry.register(tool)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate tool registration should fail")


def test_typed_input_and_output_validation_is_deterministic() -> None:
    tool = _update_tool()

    validated_input = tool.validate_input({"vendor_id": "v-1", "status": "active"})
    validated_output = tool.validate_output({"updated": True})

    assert validated_input.model_dump() == {"vendor_id": "v-1", "status": "active"}
    assert validated_output.model_dump() == {"updated": True}

    try:
        tool.validate_input({"vendor_id": "v-1"})
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid tool input should fail validation")


def test_discovery_filters_by_capability_side_effect_and_risk() -> None:
    registry = ToolRegistry()
    registry.register(_lookup_tool())
    registry.register(_update_tool())

    read_only = registry.discover(
        capabilities={"vendor.read", "vendor.write"},
        include_side_effects={SideEffectClass.READ},
    )
    assert [tool.identity for tool in read_only] == ["vendor.lookup@1.0"]

    low_risk = registry.discover(
        capabilities={"vendor.read", "vendor.write"},
        max_risk=RiskClass.MEDIUM,
    )
    assert [tool.identity for tool in low_risk] == ["vendor.lookup@1.0"]

    insufficient_capability = registry.discover(capabilities={"vendor.read"})
    assert [tool.identity for tool in insufficient_capability] == ["vendor.lookup@1.0"]


def test_resource_scoped_tools_require_resource_type() -> None:
    try:
        ToolDefinition(
            name="vendor.update",
            version="1.0",
            description="Update vendor",
            input_schema=VendorUpdateInput,
            output_schema=VendorUpdateOutput,
            side_effect=SideEffectClass.WRITE,
            risk=RiskClass.HIGH,
            required_capabilities=frozenset({"vendor.write"}),
            scope_level=ScopeLevel.RESOURCE,
        )
    except ValueError as exc:
        assert "resource_type" in str(exc)
    else:
        raise AssertionError("resource-scoped tool without resource_type should fail")
