"""Base agent class — loads YAML config, injects tools and LLM client."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from core.settings import resolve_agent_config_path
from models.agent_config import AgentConfig
from models.output_enforcer import OutputEnforcer
from tools.registry import ToolDefinition, ToolRegistry

if TYPE_CHECKING:
    from core.llm_client import LLMClient
    from core.state import OpsState

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """
    Base class for all specialist and orchestrator agents.

    Sub-classes must implement `run(state)` which receives the current
    OpsState and returns a dict of state updates.
    """

    def __init__(
        self,
        config_path: str | Path,
        llm_client: LLMClient,
    ) -> None:
        resolved_config_path = Path(config_path)
        if not resolved_config_path.is_absolute():
            resolved_config_path = resolve_agent_config_path(resolved_config_path.name)
        self.config = AgentConfig.from_yaml(str(resolved_config_path))
        self.llm_client = llm_client
        self.enforcer = OutputEnforcer(llm_client)
        self._tools: list[ToolDefinition] = self._load_tools()
        self.logger = structlog.get_logger(self.config.name)

    def _load_tools(self) -> list[ToolDefinition]:
        """Resolve whitelisted tools through ToolRegistry ACL."""
        whitelist = self.config.tools_whitelist
        if not whitelist:
            return []
        registry = ToolRegistry.get_instance()
        try:
            return registry.get_tools_for_agent(self.config.name, whitelist)
        except (PermissionError, ValueError) as exc:
            logger.error(
                "Tool loading failed",
                agent=self.config.name,
                error=str(exc),
            )
            raise

    def get_tool_descriptions(self) -> list[dict[str, str]]:
        """Return tool descriptions in OpenAI function-style format for prompts."""
        return [
            {"name": t.name, "description": t.description} for t in self._tools
        ]

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a whitelisted tool by name."""
        registry = ToolRegistry.get_instance()
        return registry.execute(tool_name, self.config.name, **kwargs)

    @property
    def model_id(self) -> str:
        if self.config.model:
            return self.config.model.model_id
        return "gpt-4o"

    @property
    def temperature(self) -> float:
        if self.config.model:
            return self.config.model.temperature
        return 0.1

    @property
    def max_tokens(self) -> int:
        if self.config.model:
            return self.config.model.max_tokens
        return 4096

    @property
    def timeout(self) -> float:
        if self.config.model:
            return float(self.config.model.timeout_seconds)
        return 60.0

    @abstractmethod
    async def run(self, state: OpsState) -> dict[str, Any]:
        """
        Execute the agent logic.

        Args:
            state: Current graph state

        Returns:
            Dict of state field updates to merge into OpsState
        """
