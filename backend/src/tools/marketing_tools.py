"""Marketing domain tools — registered with ToolRegistry at import time."""
from __future__ import annotations

from application.repositories import get_marketing_repository
from tools.registry import ToolDefinition, ToolRegistry


def get_campaign_performance(date_str: str = "2026-05-31") -> list:
    """Return performance metrics for all marketing campaigns."""
    return get_marketing_repository().get_campaign_performance(date_str)


def get_channel_metrics(date_str: str = "2026-05-31") -> list:
    """Return aggregated spend and ROAS by marketing channel."""
    return get_marketing_repository().get_channel_metrics(date_str)


def get_active_promotions(date_str: str = "2026-05-31") -> list:
    """Return all active (non-paused) campaign details."""
    return get_marketing_repository().get_active_promotions(date_str)


def list_paused_campaigns(date_str: str = "2026-05-31") -> list:
    """Return campaigns that were paused on the given date."""
    return get_marketing_repository().list_paused_campaigns(date_str)


# Phase 2: Date range tool variants
def get_campaign_performance_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return campaign performance time series over a date range."""
    return get_marketing_repository().get_campaign_performance_range(start_date, end_date, granularity)


def get_channel_metrics_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return channel metrics time series over a date range."""
    return get_marketing_repository().get_channel_metrics_range(start_date, end_date, granularity)


# ── Registration ──────────────────────────────────────────────────────────────
def register_marketing_tools() -> None:
    registry = ToolRegistry.get_instance()
    for fn, name, desc in [
        (get_campaign_performance, "get_campaign_performance", "Get campaign performance metrics"),
        (get_channel_metrics, "get_channel_metrics", "Get aggregated channel ROAS and spend"),
        (get_active_promotions, "get_active_promotions", "List active promotions"),
        (list_paused_campaigns, "list_paused_campaigns", "List paused campaigns"),
        # Phase 2: Range tools
        (get_campaign_performance_range, "get_campaign_performance_range", "Campaign performance time series (daily/weekly/monthly)"),
        (get_channel_metrics_range, "get_channel_metrics_range", "Channel metrics time series (daily/weekly/monthly)"),
    ]:
        registry.register(ToolDefinition(name=name, description=desc, function=fn))
