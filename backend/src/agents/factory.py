"""Agent factory — creates agent instances by name."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from core.llm_client import LLMClient


def create_agent(name: str, llm_client: LLMClient) -> BaseAgent:
    """
    Instantiate and return a named agent.

    Args:
        name: Agent name matching the YAML config filename
        llm_client: Shared LLMClient instance

    Returns:
        Configured BaseAgent subclass instance
    """
    # Import here to avoid circular imports at module load time
    from agents.action_executor import ActionExecutorAgent
    from agents.coordinator import CoordinatorAgent
    from agents.inventory_analyst import InventoryAnalystAgent
    from agents.marketing_analyst import MarketingAnalystAgent
    from agents.memory_agent import MemoryAgent
    from agents.query_interpreter import QueryInterpreterAgent
    from agents.reflection_agent import ReflectionAgent
    from agents.sales_analyst import SalesAnalystAgent
    from agents.support_analyst import SupportAnalystAgent
    from agents.synthesis_agent import SynthesisAgent

    _REGISTRY: dict[str, type] = {
        "query_interpreter": QueryInterpreterAgent,
        "coordinator": CoordinatorAgent,
        "sales_analyst": SalesAnalystAgent,
        "inventory_analyst": InventoryAnalystAgent,
        "marketing_analyst": MarketingAnalystAgent,
        "support_analyst": SupportAnalystAgent,
        "synthesis_agent": SynthesisAgent,
        "reflection_agent": ReflectionAgent,
        "action_executor": ActionExecutorAgent,
        "memory_agent": MemoryAgent,
    }

    agent_class = _REGISTRY.get(name)
    if agent_class is None:
        raise ValueError(
            f"Unknown agent name '{name}'. Available: {list(_REGISTRY.keys())}"
        )

    return agent_class(llm_client=llm_client)
