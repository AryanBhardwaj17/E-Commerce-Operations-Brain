"""Coordinator agent — routes queries to specialist domains."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.inventory_actions import is_inventory_action_request, parse_inventory_action_request
from core.memory_intent import is_memory_recall_request
from core.settings import resolve_agent_config_path
from models.schemas import DomainType, IntentType, RoutingDecision

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("coordinator.yaml")


class CoordinatorAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        requery_hints = state.get("coordinator_requery_hints")
        query_intent = state.get("query_intent")  # Phase 1 - structured intent
        self.logger.info("Coordinator routing query", query=query, has_query_intent=query_intent is not None)

        direct_inventory_action = parse_inventory_action_request(query)
        if direct_inventory_action is not None and is_inventory_action_request(query):
            inventory_routing = RoutingDecision(
                intent=IntentType.ACTION,
                active_domains=[DomainType.INVENTORY],
                reasoning=direct_inventory_action["routing_reason"],
                requires_memory_lookup=False,
                requires_action=True,
            )
            return {
                "routing_decision": inventory_routing,
                "active_domains": [DomainType.INVENTORY.value],
                "coordinator_requery_hints": None,
            }

        # Memory-recall questions ("what did we do last time", "which actions worked
        # best in past incidents") are answered from KEDB/KADB rather than running a
        # fresh diagnostic. Memory context was already retrieved by the memory_reader,
        # so route straight to the dedicated memory-response path with no domains.
        if is_memory_recall_request(query):
            memory_routing = RoutingDecision(
                intent=IntentType.MEMORY,
                active_domains=[],
                reasoning=(
                    "The user is asking to recall past incidents, decisions, or outcomes. "
                    "Answer from memory (KEDB/KADB) instead of running a new diagnostic."
                ),
                requires_memory_lookup=True,
                requires_action=False,
            )
            return {
                "routing_decision": memory_routing,
                "active_domains": [],
                "coordinator_requery_hints": None,
            }

        # Phase 1 - Build context with query_intent if available
        intent_context = ""
        if query_intent:
            intent_context = (
                "\n\nQuery Intent (parsed by query_interpreter):\n"
                f"{json.dumps(query_intent, indent=2, default=str)}\n\n"
                "Use this structured intent to inform your routing:\n"
                "- If requested_metrics are specified, route to domains that provide those metrics\n"
                "- If is_diagnostic=true, include all potentially relevant domains for root-cause analysis\n"
                "- If response_format='list' and query mentions inventory, strongly favor INVENTORY domain"
            )

        requery_context = ""
        if requery_hints:
            requery_context = (
                "\n\nReflection requested a coordinator re-check. Re-evaluate the routing from scratch, "
                "using these hints without blindly copying them:\n"
                f"{json.dumps(requery_hints, indent=2, default=str)}"
            )

        messages = [
            {
                "role": "system",
                "content": self.config.system_prompt or "",
            },
            {
                "role": "user",
                "content": (
                    f"Business query: {query}\n\n"
                    f"Analyse this query and return a RoutingDecision JSON."
                    f"{intent_context}"  # Phase 1 - include structured intent
                    f"{requery_context}"
                ),
            },
        ]

        routing: RoutingDecision = await self.enforcer.enforce(
            messages=messages,
            output_schema=RoutingDecision,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        self.logger.info(
            "Routing decision",
            intent=routing.intent,
            domains=[d.value for d in routing.active_domains],
        )

        return {
            "routing_decision": routing,
            "active_domains": [d.value for d in routing.active_domains],
            "coordinator_requery_hints": None,
        }
