"""Marketing analyst agent."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import DomainFinding

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("marketing_analyst.yaml")


def _memory_summary(memory_ctx: Any) -> str:
    if not memory_ctx:
        return "No prior context available."

    summary_parts: list[str] = []
    if getattr(memory_ctx, "kedb_matches", None):
        summary_parts.append(f"KEDB matches: {len(memory_ctx.kedb_matches)}")
    if getattr(memory_ctx, "kadb_matches", None):
        summary_parts.append(f"KADB matches: {len(memory_ctx.kadb_matches)}")

    return "; ".join(summary_parts) if summary_parts else "No prior context available."


class MarketingAnalystAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        date_str = state.get("date_str", "2026-05-31")
        memory_ctx = state.get("memory_context")

        self.logger.info("Marketing analyst running", date=date_str)

        tool_data = {
            "campaign_performance": self.call_tool("get_campaign_performance", date_str=date_str),
            "channel_metrics": self.call_tool("get_channel_metrics", date_str=date_str),
            "active_promotions": self.call_tool("get_active_promotions", date_str=date_str),
            "paused_campaigns": self.call_tool("list_paused_campaigns", date_str=date_str),
        }

        memory_summary = _memory_summary(memory_ctx)

        messages = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n"
                    f"Analysis date: {date_str}\n\n"
                    f"Historical context:\n{memory_summary}\n\n"
                    f"Marketing data:\n{json.dumps(tool_data, indent=2, default=str)}\n\n"
                    f"Produce a DomainFinding JSON for domain=MARKETING."
                ),
            },
        ]

        finding: DomainFinding = await self.enforcer.enforce(
            messages=messages,
            output_schema=DomainFinding,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        self.logger.info("Marketing finding produced", confidence=finding.confidence)
        return {"domain_findings": {"MARKETING": finding}}
