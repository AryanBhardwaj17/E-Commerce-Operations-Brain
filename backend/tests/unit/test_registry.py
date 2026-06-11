"""Unit tests for ToolRegistry and ToolACL."""
from __future__ import annotations

import pytest

from tools.registry import ToolACL, ToolDefinition, ToolRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton between tests."""
    ToolRegistry.reset()
    yield
    ToolRegistry.reset()


def _make_tool(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=f"Test {name}", function=lambda: name)


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_and_retrieve():
    registry = ToolRegistry.get_instance()
    registry.register(_make_tool("my_tool"))
    assert "my_tool" in registry.all_names()


def test_execute_registered_tool():
    registry = ToolRegistry.get_instance()
    registry.register(ToolDefinition(name="add", description="add", function=lambda x, y: x + y))
    result = registry.execute("add", "admin", x=1, y=2)
    assert result == 3


def test_execute_unregistered_tool_raises():
    registry = ToolRegistry.get_instance()
    with pytest.raises(ValueError, match="not found"):
        registry.execute("nonexistent", "admin")


# ── ACL ───────────────────────────────────────────────────────────────────────

def _make_acl(allowed_tools: list[str]) -> ToolACL:
    config = {
        "roles": {"test_role": {"tools": allowed_tools}},
        "agents": {"test_agent": {"role": "test_role"}},
    }
    return ToolACL(config)


def test_acl_allows_whitelisted_tool():
    acl = _make_acl(["tool_a", "tool_b"])
    assert acl.is_allowed("test_agent", "tool_a")


def test_acl_denies_non_whitelisted_tool():
    acl = _make_acl(["tool_a"])
    assert not acl.is_allowed("test_agent", "tool_b")


def test_acl_admin_wildcard():
    acl = _make_acl(["*"])
    assert acl.is_allowed("test_agent", "any_tool")


def test_acl_unknown_agent_denies():
    acl = _make_acl(["tool_a"])
    assert not acl.is_allowed("unknown_agent", "tool_a")


def test_get_tools_for_agent_raises_on_permission_violation():
    registry = ToolRegistry.get_instance()
    registry.register(_make_tool("forbidden_tool"))
    acl = _make_acl(["other_tool"])
    registry.set_acl(acl)

    with pytest.raises(PermissionError):
        registry.get_tools_for_agent("test_agent", ["forbidden_tool"])


def test_get_tools_for_agent_raises_on_unregistered():
    registry = ToolRegistry.get_instance()
    acl = _make_acl(["ghost_tool"])
    registry.set_acl(acl)

    with pytest.raises(ValueError, match="not registered"):
        registry.get_tools_for_agent("test_agent", ["ghost_tool"])
