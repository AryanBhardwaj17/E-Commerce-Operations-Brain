"""Support domain tools — registered with ToolRegistry at import time."""
from __future__ import annotations

from application.repositories import get_support_repository
from tools.registry import ToolDefinition, ToolRegistry


def get_complaint_trends(date_str: str = "2026-05-31") -> dict:
    """Return complaint volume and category breakdown for a given date."""
    return get_support_repository().get_complaint_trends(date_str)


def get_refund_metrics(date_str: str = "2026-05-31") -> dict:
    """Return refund request volume and rate for a given date."""
    return get_support_repository().get_refund_metrics(date_str)


def get_review_sentiment(date_str: str = "2026-05-31") -> dict:
    """Return customer review sentiment scores and topic breakdown."""
    return get_support_repository().get_review_sentiment(date_str)


# Phase 2: Date range tool variants
def get_complaint_trends_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return complaint trends time series over a date range."""
    return get_support_repository().get_complaint_trends_range(start_date, end_date, granularity)


def get_refund_metrics_range(
    start_date: str, end_date: str, granularity: str = "daily"
) -> list:
    """Return refund metrics time series over a date range."""
    return get_support_repository().get_refund_metrics_range(start_date, end_date, granularity)


# ── Registration ──────────────────────────────────────────────────────────────
def register_support_tools() -> None:
    registry = ToolRegistry.get_instance()
    for fn, name, desc in [
        (get_complaint_trends, "get_complaint_trends", "Get complaint volume and trends"),
        (get_refund_metrics, "get_refund_metrics", "Get refund rate and volume"),
        (get_review_sentiment, "get_review_sentiment", "Get customer review sentiment"),
        # Phase 2: Range tools
        (get_complaint_trends_range, "get_complaint_trends_range", "Complaint trends time series (daily/weekly/monthly)"),
        (get_refund_metrics_range, "get_refund_metrics_range", "Refund metrics time series (daily/weekly/monthly)"),
    ]:
        registry.register(ToolDefinition(name=name, description=desc, function=fn))
