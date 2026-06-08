"""Central tool registry with deny-by-default ACL enforcement."""
from __future__ import annotations

from typing import Any

import structlog
import yaml
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


# ── Tool Definition ───────────────────────────────────────────────────────────

class ToolDefinition(BaseModel):
    name: str
    description: str
    function: Any  # Callable — Pydantic requires arbitrary_types_allowed
    input_schema: type[BaseModel] | None = None

    model_config = {"arbitrary_types_allowed": True}


# ── ACL ───────────────────────────────────────────────────────────────────────

class ToolACL:
    """
    Role-based tool access control.

    Roles map to explicit tool lists.
    Agents map to roles.
    Any tool not in the role's list is DENIED.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._roles: dict[str, list[str]] = {}
        self._agent_roles: dict[str, str] = {}
        self._load(config)

    def _load(self, config: dict[str, Any]) -> None:
        for role_name, role_cfg in config.get("roles", {}).items():
            self._roles[role_name] = role_cfg.get("tools", [])
        for agent_name, agent_cfg in config.get("agents", {}).items():
            if isinstance(agent_cfg, dict):
                self._agent_roles[agent_name] = agent_cfg.get("role", "")

    def get_allowed_tools(self, agent_name: str) -> set[str]:
        role = self._agent_roles.get(agent_name)
        if not role:
            return set()
        tools = self._roles.get(role, [])
        if tools == ["*"]:
            return {"*"}
        return set(tools)

    def is_allowed(self, agent_name: str, tool_name: str) -> bool:
        allowed = self.get_allowed_tools(agent_name)
        return "*" in allowed or tool_name in allowed

    @classmethod
    def from_yaml(cls, path: str) -> ToolACL:
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))


# ── Registry ──────────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Singleton registry for all tool definitions.

    Usage:
        registry = ToolRegistry.get_instance()
        registry.register(ToolDefinition(name="my_tool", ...))
        tools = registry.get_tools_for_agent("sales_analyst", whitelist)
        result = registry.execute("get_revenue_metrics", "sales_analyst", date="2026-05-31")
    """

    _instance: ToolRegistry | None = None

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._acl: ToolACL | None = None

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — used in tests."""
        cls._instance = None

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_acl(self, acl: ToolACL) -> None:
        self._acl = acl

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        logger.debug("Tool registered", tool=tool.name)

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_tools_for_agent(
        self, agent_name: str, whitelist: list[str]
    ) -> list[ToolDefinition]:
        """
        Returns ToolDefinition objects for the given whitelist.
        Raises PermissionError if ACL denies any tool.
        Raises ValueError if a whitelisted tool is not registered.
        """
        result: list[ToolDefinition] = []
        for name in whitelist:
            if name not in self._tools:
                raise ValueError(
                    f"Tool '{name}' in whitelist for agent '{agent_name}' "
                    f"is not registered in ToolRegistry."
                )
            if self._acl and not self._acl.is_allowed(agent_name, name):
                raise PermissionError(
                    f"Agent '{agent_name}' is not authorized to use tool '{name}'. "
                    f"Allowed tools: {self._acl.get_allowed_tools(agent_name)}"
                )
            result.append(self._tools[name])
        return result

    def get(self, tool_name: str) -> ToolDefinition | None:
        return self._tools.get(tool_name)

    def all_names(self) -> list[str]:
        return list(self._tools.keys())

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute(self, tool_name: str, agent_name: str, **kwargs: Any) -> Any:
        """Execute a tool with ACL enforcement."""
        if self._acl and not self._acl.is_allowed(agent_name, tool_name):
            raise PermissionError(
                f"Agent '{agent_name}' is not authorized to call tool '{tool_name}'."
            )
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' not found in registry.")
        logger.info("Executing tool", tool=tool_name, agent=agent_name)
        return tool.function(**kwargs)
