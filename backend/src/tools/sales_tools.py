"""Sales domain tools — thin wrappers over mock data, registered with ToolRegistry."""
from __future__ import annotations

from typing import Any

from application.repositories import get_sales_repository
from tools.registry import ToolDefinition, ToolRegistry


def get_revenue_metrics(date_str: str) -> dict[str, Any]:
    """Return revenue metrics for the given date including anomaly flags."""
    return get_sales_repository().get_revenue_metrics(date_str)


def get_order_volume(date_str: str) -> dict[str, Any]:
    """Return total order volume and week-over-week comparison for the given date."""
    return get_sales_repository().get_order_volume(date_str)


def get_regional_sales(date_str: str) -> list[dict[str, Any]]:
    """Return per-region revenue breakdown for the given date."""
    return get_sales_repository().get_regional_sales(date_str)


def get_product_performance(date_str: str) -> list[dict[str, Any]]:
    """Return per-SKU revenue and order counts for the given date."""
    return get_sales_repository().get_product_performance(date_str)


def detect_sales_anomaly(date_str: str) -> dict[str, Any]:
    """Detect and characterise any revenue anomaly on the given date."""
    return get_sales_repository().detect_sales_anomaly(date_str)


# Phase 2: Date range tool variants
def get_revenue_metrics_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list[dict[str, Any]]:
    """Return revenue metrics time series over a date range."""
    return get_sales_repository().get_revenue_metrics_range(start_date, end_date, granularity)


def get_order_volume_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list[dict[str, Any]]:
    """Return order volume time series over a date range."""
    return get_sales_repository().get_order_volume_range(start_date, end_date, granularity)


def get_regional_sales_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list[dict[str, Any]]:
    """Return regional sales time series over a date range."""
    return get_sales_repository().get_regional_sales_range(start_date, end_date, granularity)


def get_product_performance_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list[dict[str, Any]]:
    """Return product performance time series over a date range."""
    return get_sales_repository().get_product_performance_range(start_date, end_date, granularity)


def register_sales_tools() -> None:
    """Register all sales tools with the ToolRegistry singleton."""
    registry = ToolRegistry.get_instance()

    registry.register(ToolDefinition(
        name="get_revenue_metrics",
        description="Revenue metrics for a date: total, vs-yesterday, vs-last-week, anomaly flag.",
        function=get_revenue_metrics,
    ))

    registry.register(ToolDefinition(
        name="get_order_volume",
        description="Order volume and average order value for a date.",
        function=get_order_volume,
    ))

    registry.register(ToolDefinition(
        name="get_regional_sales",
        description="Per-region revenue breakdown for a date.",
        function=get_regional_sales,
    ))

    registry.register(ToolDefinition(
        name="get_product_performance",
        description="Per-SKU revenue, orders, and contribution for a date.",
        function=get_product_performance,
    ))

    registry.register(ToolDefinition(
        name="detect_sales_anomaly",
        description="Detect revenue anomaly: severity, cause, affected regions and products.",
        function=detect_sales_anomaly,
    ))

    # Phase 2: Register date range tools
    registry.register(ToolDefinition(
        name="get_revenue_metrics_range",
        description="Revenue metrics time series over date range (daily/weekly/monthly granularity).",
        function=get_revenue_metrics_range,
    ))

    registry.register(ToolDefinition(
        name="get_order_volume_range",
        description="Order volume time series over date range (daily/weekly/monthly granularity).",
        function=get_order_volume_range,
    ))

    registry.register(ToolDefinition(
        name="get_regional_sales_range",
        description="Regional sales time series over date range (daily/weekly/monthly granularity).",
        function=get_regional_sales_range,
    ))

    registry.register(ToolDefinition(
        name="get_product_performance_range",
        description="Product performance time series over date range (daily/weekly/monthly granularity).",
        function=get_product_performance_range,
    ))
