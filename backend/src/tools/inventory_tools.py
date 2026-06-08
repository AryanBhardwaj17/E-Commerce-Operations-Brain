"""Inventory domain tools — registered with ToolRegistry at import time."""
from __future__ import annotations

from application.repositories import get_inventory_repository
from tools.registry import ToolDefinition, ToolRegistry


def get_stock_levels(date_str: str = "2026-05-31") -> list:
    """Return stock levels and health status for all SKUs."""
    return get_inventory_repository().get_stock_levels(date_str)


def get_stockout_items(date_str: str = "2026-05-31") -> list:
    """Return SKUs that are currently out of stock."""
    return get_inventory_repository().get_stockout_items(date_str)


def get_low_stock_alerts(date_str: str = "2026-05-31") -> list:
    """Return SKUs at or below reorder point."""
    return get_inventory_repository().get_low_stock_alerts(date_str)


def get_conversion_impact(date_str: str = "2026-05-31") -> dict:
    """Estimate revenue and conversion rate lost due to stockouts."""
    return get_inventory_repository().get_conversion_impact(date_str)


# Phase 2: Date range tool variants
def get_stock_levels_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return stock levels time series over a date range."""
    return get_inventory_repository().get_stock_levels_range(start_date, end_date, granularity)


def get_stockout_trends_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return stockout trends time series over a date range."""
    return get_inventory_repository().get_stockout_trends_range(start_date, end_date, granularity)


# ── Registration ──────────────────────────────────────────────────────────────
def register_inventory_tools() -> None:
    registry = ToolRegistry.get_instance()
    for fn, name, desc in [
        (get_stock_levels, "get_stock_levels", "Get stock levels for all SKUs"),
        (get_stockout_items, "get_stockout_items", "Get currently out-of-stock SKUs"),
        (get_low_stock_alerts, "get_low_stock_alerts", "Get low-stock and stockout alerts"),
        (get_conversion_impact, "get_conversion_impact", "Estimate revenue lost to stockouts"),
        # Phase 2: Range tools
        (get_stock_levels_range, "get_stock_levels_range", "Stock levels time series (daily/weekly/monthly)"),
        (get_stockout_trends_range, "get_stockout_trends_range", "Stockout trends time series (daily/weekly/monthly)"),
    ]:
        registry.register(ToolDefinition(name=name, description=desc, function=fn))
