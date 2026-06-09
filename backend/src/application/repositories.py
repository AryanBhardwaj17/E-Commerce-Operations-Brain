"""Repository ports and runtime registry for commerce data access."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class SalesRepository(Protocol):
    def get_revenue_metrics(self, date_str: str) -> dict[str, Any]: ...

    def get_order_volume(self, date_str: str) -> dict[str, Any]: ...

    def get_regional_sales(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_product_performance(self, date_str: str) -> list[dict[str, Any]]: ...

    def detect_sales_anomaly(self, date_str: str) -> dict[str, Any]: ...

    # Phase 2: Date range variants
    def get_revenue_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_order_volume_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_regional_sales_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_product_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...


class InventoryRepository(Protocol):
    def get_stock_levels(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_stockout_items(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_low_stock_alerts(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_conversion_impact(self, date_str: str) -> dict[str, Any]: ...

    def add_inventory_item(
        self,
        *,
        product_name: str,
        product_id: str | None = None,
        quantity_available: int = 100,
        reorder_point: int = 25,
        lead_days: int = 5,
    ) -> dict[str, Any]: ...

    def increase_inventory_quantity(
        self,
        *,
        product_id: str,
        quantity_delta: int,
    ) -> dict[str, Any]: ...

    def decrease_inventory_quantity(
        self,
        *,
        product_id: str,
        quantity_delta: int,
    ) -> dict[str, Any]: ...

    def remove_inventory_item(
        self,
        *,
        product_id: str,
        reason: str = "",
    ) -> dict[str, Any]: ...

    def update_inventory_price(
        self,
        *,
        product_id: str,
        unit_price: float,
        currency: str = "USD",
    ) -> dict[str, Any]: ...

    def create_discount_plan(
        self,
        *,
        product_id: str,
        discount_pct: float,
        plan_name: str | None = None,
        starts_on: str | None = None,
        ends_on: str | None = None,
    ) -> dict[str, Any]: ...

    def update_discount_plan(
        self,
        *,
        discount_plan_id: str | None = None,
        product_id: str | None = None,
        discount_pct: float | None = None,
        plan_name: str | None = None,
        starts_on: str | None = None,
        ends_on: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]: ...

    def deactivate_discount_plan(
        self,
        *,
        discount_plan_id: str | None = None,
        product_id: str | None = None,
    ) -> dict[str, Any]: ...

    def list_discount_plans(
        self,
        *,
        product_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]: ...

    # Phase 2: Date range variants
    def get_stock_levels_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_stockout_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...


class MarketingRepository(Protocol):
    def get_campaign_performance(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_channel_metrics(self, date_str: str) -> list[dict[str, Any]]: ...

    def get_active_promotions(self, date_str: str) -> list[dict[str, Any]]: ...

    def list_paused_campaigns(self, date_str: str) -> list[dict[str, Any]]: ...

    # Campaign control actions
    def pause_campaign(
        self,
        *,
        campaign_id: str,
        reason: str = "",
    ) -> dict[str, Any]: ...

    def resume_campaign(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]: ...

    def get_campaign_status(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]: ...

    # Phase 2: Date range variants
    def get_campaign_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_channel_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...


class SupportRepository(Protocol):
    def get_complaint_trends(self, date_str: str) -> dict[str, Any]: ...

    def get_refund_metrics(self, date_str: str) -> dict[str, Any]: ...

    def get_review_sentiment(self, date_str: str) -> dict[str, Any]: ...

    # Support ticket actions
    def create_support_ticket(
        self,
        *,
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "general",
        assigned_to: str | None = None,
    ) -> dict[str, Any]: ...

    def get_ticket_status(
        self,
        *,
        ticket_id: str,
    ) -> dict[str, Any]: ...

    # Phase 2: Date range variants
    def get_complaint_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...

    def get_refund_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class RepositoryRegistry:
    sales: SalesRepository
    inventory: InventoryRepository
    marketing: MarketingRepository
    support: SupportRepository


_repository_registry: RepositoryRegistry | None = None


def configure_repository_registry(registry: RepositoryRegistry) -> RepositoryRegistry:
    global _repository_registry
    _repository_registry = registry
    return registry


def reset_repository_registry() -> None:
    global _repository_registry
    _repository_registry = None


def get_repository_registry() -> RepositoryRegistry:
    if _repository_registry is None:
        from infrastructure.repositories import build_repository_registry  # noqa: PLC0415

        configure_repository_registry(build_repository_registry())
    registry = _repository_registry
    if registry is None:
        raise RuntimeError("Repository registry is not configured.")
    return registry


def get_sales_repository() -> SalesRepository:
    return get_repository_registry().sales


def get_inventory_repository() -> InventoryRepository:
    return get_repository_registry().inventory


def get_marketing_repository() -> MarketingRepository:
    return get_repository_registry().marketing


def get_support_repository() -> SupportRepository:
    return get_repository_registry().support
