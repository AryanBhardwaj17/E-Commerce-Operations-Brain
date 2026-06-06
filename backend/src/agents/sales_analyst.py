"""Sales analyst agent."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import DomainFinding

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("sales_analyst.yaml")


def _memory_summary(memory_ctx: Any) -> str:
    if not memory_ctx:
        return "No prior context available."

    summary_parts: list[str] = []
    if getattr(memory_ctx, "kedb_matches", None):
        summary_parts.append(f"KEDB matches: {len(memory_ctx.kedb_matches)}")
    if getattr(memory_ctx, "kadb_matches", None):
        summary_parts.append(f"KADB matches: {len(memory_ctx.kadb_matches)}")

    return "; ".join(summary_parts) if summary_parts else "No prior context available."


class SalesAnalystAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        date_str = state.get("date_str", "2026-05-31")
        memory_ctx = state.get("memory_context")
        query_intent = state.get("query_intent")  # Phase 2

        self.logger.info("Sales analyst running", date=date_str, has_query_intent=query_intent is not None)

        # Phase 2: Determine which tools to call based on query_intent
        tool_data = {}

        if query_intent:
            # Request-driven: call tools based on requested_metrics and temporal_scope
            requested_metrics = query_intent.get("requested_metrics", [])
            temporal_scope = query_intent.get("temporal_scope")

            # Map metrics to tools
            sales_metrics = {
                "revenue": "get_revenue_metrics",
                "order_volume": "get_order_volume",
                "average_order_value": "get_order_volume",
                "conversion_rate": "get_revenue_metrics",
                "regional_sales": "get_regional_sales",
                "product_performance": "get_product_performance",
            }

            # If temporal_scope has a date range, use range tools
            if temporal_scope and temporal_scope.get("start_date") and temporal_scope.get("end_date"):
                start_date = temporal_scope["start_date"]
                end_date = temporal_scope["end_date"]
                granularity = temporal_scope.get("granularity", "daily")

                # Collect unique tools needed
                tools_to_call = set()
                if not requested_metrics:
                    # No specific metrics requested, call default range tools
                    tools_to_call = {"get_revenue_metrics", "get_order_volume"}
                else:
                    for metric in requested_metrics:
                        if tool := sales_metrics.get(metric.lower()):
                            tools_to_call.add(tool)

                # Call range variants
                if "get_revenue_metrics" in tools_to_call:
                    tool_data["revenue_metrics_range"] = self.call_tool(
                        "get_revenue_metrics_range",
                        start_date=start_date,
                        end_date=end_date,
                        granularity=granularity,
                    )
                if "get_order_volume" in tools_to_call:
                    tool_data["order_volume_range"] = self.call_tool(
                        "get_order_volume_range",
                        start_date=start_date,
                        end_date=end_date,
                        granularity=granularity,
                    )
                if "get_regional_sales" in tools_to_call:
                    tool_data["regional_sales_range"] = self.call_tool(
                        "get_regional_sales_range",
                        start_date=start_date,
                        end_date=end_date,
                        granularity=granularity,
                    )
                if "get_product_performance" in tools_to_call:
                    tool_data["product_performance_range"] = self.call_tool(
                        "get_product_performance_range",
                        start_date=start_date,
                        end_date=end_date,
                        granularity=granularity,
                    )
            else:
                # Single-date query with specific metrics
                if "revenue" in [m.lower() for m in requested_metrics]:
                    tool_data["revenue_metrics"] = self.call_tool("get_revenue_metrics", date_str=date_str)
                if "order_volume" in [m.lower() for m in requested_metrics] or "average_order_value" in [m.lower() for m in requested_metrics]:
                    tool_data["order_volume"] = self.call_tool("get_order_volume", date_str=date_str)
                if "regional_sales" in [m.lower() for m in requested_metrics]:
                    tool_data["regional_sales"] = self.call_tool("get_regional_sales", date_str=date_str)
                if "product_performance" in [m.lower() for m in requested_metrics]:
                    tool_data["product_performance"] = self.call_tool("get_product_performance", date_str=date_str)

                # If no specific metrics, call all (backward compatibility)
                if not requested_metrics:
                    tool_data = {
                        "revenue_metrics": self.call_tool("get_revenue_metrics", date_str=date_str),
                        "order_volume": self.call_tool("get_order_volume", date_str=date_str),
                        "regional_sales": self.call_tool("get_regional_sales", date_str=date_str),
                        "product_performance": self.call_tool("get_product_performance", date_str=date_str),
                    }
        else:
            # Legacy: call all tools (backward compatibility)
            tool_data = {
                "revenue_metrics": self.call_tool("get_revenue_metrics", date_str=date_str),
                "order_volume": self.call_tool("get_order_volume", date_str=date_str),
                "regional_sales": self.call_tool("get_regional_sales", date_str=date_str),
                "product_performance": self.call_tool("get_product_performance", date_str=date_str),
                "anomaly_detection": self.call_tool("detect_sales_anomaly", date_str=date_str),
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
                    f"Sales data:\n{json.dumps(tool_data, indent=2, default=str)}\n\n"
                    f"Produce a DomainFinding JSON for domain=SALES."
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

        self.logger.info("Sales finding produced", confidence=finding.confidence)
        return {"domain_findings": {"SALES": finding}}
