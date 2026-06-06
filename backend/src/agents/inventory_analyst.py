"""Inventory analyst agent."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import DataPoint, DomainFinding, DomainType

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("inventory_analyst.yaml")

_INVENTORY_LIST_PATTERNS = (
    r"\ball items\b",
    r"\ball products\b",
    r"\ball skus\b",
    r"\bevery item\b",
    r"\binventory list\b",
    r"\bstock list\b",
    r"\bstock levels\b",
    r"\blist\b",
    r"\bshow\b",
    r"\bdisplay\b",
)


def query_requests_inventory_list(query: str) -> bool:
    normalized_query = " ".join(query.lower().split())
    has_inventory_context = any(
        term in normalized_query for term in ("inventory", "stock", "sku", "item", "product")
    )
    return has_inventory_context and any(
        re.search(pattern, normalized_query) for pattern in _INVENTORY_LIST_PATTERNS
    )


def _normalize_stock_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": item.get("product_id", ""),
        "product_name": item.get("product_name", "Unknown product"),
        "quantity_available": item.get("quantity_available", 0),
        "reorder_point": item.get("reorder_point", 0),
        "status": item.get("status", "unknown"),
        "days_until_stockout": item.get("days_until_stockout"),
        "unit_price": item.get("unit_price"),
        "currency": item.get("currency"),
        "effective_price": item.get("effective_price"),
        "active_discount": item.get("active_discount"),
    }


def _memory_summary(memory_ctx: Any) -> str:
    if not memory_ctx:
        return "No prior context available."

    summary_parts: list[str] = []
    if getattr(memory_ctx, "kedb_matches", None):
        summary_parts.append(f"KEDB matches: {len(memory_ctx.kedb_matches)}")
    if getattr(memory_ctx, "kadb_matches", None):
        summary_parts.append(f"KADB matches: {len(memory_ctx.kadb_matches)}")

    return "; ".join(summary_parts) if summary_parts else "No prior context available."


def _build_inventory_snapshot_finding(
    date_str: str,
    tool_data: dict[str, Any],
) -> DomainFinding:
    stock_levels = [_normalize_stock_item(item) for item in tool_data["stock_levels"]]
    stockout_items = [_normalize_stock_item(item) for item in tool_data["stockout_items"]]
    low_stock_items = [_normalize_stock_item(item) for item in tool_data["low_stock_alerts"]]
    healthy_count = sum(1 for item in stock_levels if item["status"] == "healthy")
    conversion_impact = tool_data["conversion_impact"]

    data_points = [
        DataPoint(metric="Total Products", value=len(stock_levels), unit="items", period=date_str),
        DataPoint(metric="Healthy Products", value=healthy_count, unit="items", period=date_str),
        DataPoint(metric="Stockout Products", value=len(stockout_items), unit="items", period=date_str),
        DataPoint(metric="Low Stock Alerts", value=len(low_stock_items), unit="items", period=date_str),
        DataPoint(
            metric="Estimated Lost Revenue",
            value=conversion_impact.get("estimated_lost_revenue", 0),
            unit="USD",
            period=date_str,
        ),
        DataPoint(
            metric="Estimated Lost Orders",
            value=conversion_impact.get("estimated_lost_orders", 0),
            unit="orders",
            period=date_str,
        ),
    ]
    data_points.extend(
        DataPoint(
            metric=item["product_name"],
            value=item,
            unit="inventory_item",
            period=date_str,
        )
        for item in stock_levels
    )

    anomalies: list[str] = []
    if stockout_items:
        anomalies.append(
            "Out of stock: "
            + ", ".join(item["product_name"] for item in stockout_items)
        )
    if low_stock_items:
        anomalies.append(
            "Below reorder point: "
            + ", ".join(item["product_name"] for item in low_stock_items)
        )

    summary = (
        f"Inventory snapshot for {date_str}: {len(stock_levels)} items tracked, "
        f"{len(stockout_items)} stockouts, and {len(low_stock_items)} items below reorder point. "
        "See the item-level inventory list below."
    )

    return DomainFinding(
        domain=DomainType.INVENTORY,
        summary=summary,
        data_points=data_points,
        anomalies=anomalies,
        contributing_factors=[],
        confidence=1.0,
        tools_called=[
            "get_stock_levels",
            "get_stockout_items",
            "get_low_stock_alerts",
            "get_conversion_impact",
        ],
    )


class InventoryAnalystAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        date_str = state.get("date_str", "2026-05-31")
        memory_ctx = state.get("memory_context")
        wants_inventory_list = query_requests_inventory_list(query)

        self.logger.info("Inventory analyst running", date=date_str)

        tool_data = {
            "stock_levels": self.call_tool("get_stock_levels", date_str=date_str),
            "stockout_items": self.call_tool("get_stockout_items", date_str=date_str),
            "low_stock_alerts": self.call_tool("get_low_stock_alerts", date_str=date_str),
            "conversion_impact": self.call_tool("get_conversion_impact", date_str=date_str),
        }

        memory_summary = _memory_summary(memory_ctx)

        if wants_inventory_list:
            inventory_finding = _build_inventory_snapshot_finding(date_str, tool_data)
            self.logger.info("Inventory listing produced", item_count=len(tool_data["stock_levels"]))
            return {
                "domain_findings": {"INVENTORY": inventory_finding},
                "inventory_items": tool_data["stock_levels"],
            }

        messages = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n"
                    f"Analysis date: {date_str}\n\n"
                    f"Historical context:\n{memory_summary}\n\n"
                    f"Inventory data:\n{json.dumps(tool_data, indent=2, default=str)}\n\n"
                    f"User expectation: {'Provide a direct inventory listing response and avoid root-cause framing unless there is a real anomaly.' if wants_inventory_list else 'Diagnose inventory health and explain the most important issue.'}\n\n"
                    f"Produce a DomainFinding JSON for domain=INVENTORY."
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

        self.logger.info("Inventory finding produced", confidence=finding.confidence)
        return {
            "domain_findings": {"INVENTORY": finding},
            "inventory_items": tool_data["stock_levels"] if wants_inventory_list else [],
        }
