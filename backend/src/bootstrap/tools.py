"""Tool registry composition helpers."""
from __future__ import annotations

from core.settings import resolve_config_path
from tools.action_tools import register_action_tools
from tools.inventory_tools import register_inventory_tools
from tools.marketing_tools import register_marketing_tools
from tools.memory_tools import register_memory_tools
from tools.registry import ToolACL, ToolRegistry
from tools.sales_tools import register_sales_tools
from tools.support_tools import register_support_tools


def initialize_tool_registry() -> ToolRegistry:
    """Configure ACLs and register all backend tools."""
    registry = ToolRegistry.get_instance()
    acl = ToolACL.from_yaml(str(resolve_config_path("tool_permissions.yaml")))
    registry.set_acl(acl)

    register_sales_tools()
    register_inventory_tools()
    register_marketing_tools()
    register_support_tools()
    register_action_tools()
    register_memory_tools()
    return registry
