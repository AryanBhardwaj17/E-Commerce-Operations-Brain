"""Mock inventory repository adapter."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from data.mock import inventory as inventory_data


class MockInventoryRepository:
    def get_stock_levels(self, date_str: str) -> list[dict[str, Any]]:
        return inventory_data.get_stock_levels(date_str)

    def get_stockout_items(self, date_str: str) -> list[dict[str, Any]]:
        return inventory_data.get_stockout_items(date_str)

    def get_low_stock_alerts(self, date_str: str) -> list[dict[str, Any]]:
        return inventory_data.get_low_stock_alerts(date_str)

    def get_conversion_impact(self, date_str: str) -> dict[str, Any]:
        return inventory_data.get_conversion_impact(date_str)

    def add_inventory_item(
        self,
        *,
        product_name: str,
        product_id: str | None = None,
        quantity_available: int = 100,
        reorder_point: int = 25,
        lead_days: int = 5,
    ) -> dict[str, Any]:
        return inventory_data.add_inventory_item(
            product_name=product_name,
            product_id=product_id,
            quantity_available=quantity_available,
            reorder_point=reorder_point,
            lead_days=lead_days,
        )

    def increase_inventory_quantity(
        self,
        *,
        product_id: str,
        quantity_delta: int,
    ) -> dict[str, Any]:
        return inventory_data.increase_inventory_quantity(
            product_id=product_id,
            quantity_delta=quantity_delta,
        )

    def decrease_inventory_quantity(
        self,
        *,
        product_id: str,
        quantity_delta: int,
    ) -> dict[str, Any]:
        return inventory_data.decrease_inventory_quantity(
            product_id=product_id,
            quantity_delta=quantity_delta,
        )

    def remove_inventory_item(
        self,
        *,
        product_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        return inventory_data.remove_inventory_item(
            product_id=product_id,
            reason=reason,
        )

    def update_inventory_price(
        self,
        *,
        product_id: str,
        unit_price: float,
        currency: str = "USD",
    ) -> dict[str, Any]:
        return inventory_data.update_inventory_price(
            product_id=product_id,
            unit_price=unit_price,
            currency=currency,
        )

    def create_discount_plan(
        self,
        *,
        product_id: str,
        discount_pct: float,
        plan_name: str | None = None,
        starts_on: str | None = None,
        ends_on: str | None = None,
    ) -> dict[str, Any]:
        return inventory_data.create_discount_plan(
            product_id=product_id,
            discount_pct=discount_pct,
            plan_name=plan_name,
            starts_on=starts_on,
            ends_on=ends_on,
        )

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
    ) -> dict[str, Any]:
        return inventory_data.update_discount_plan(
            discount_plan_id=discount_plan_id,
            product_id=product_id,
            discount_pct=discount_pct,
            plan_name=plan_name,
            starts_on=starts_on,
            ends_on=ends_on,
            active=active,
        )

    def deactivate_discount_plan(
        self,
        *,
        discount_plan_id: str | None = None,
        product_id: str | None = None,
    ) -> dict[str, Any]:
        return inventory_data.deactivate_discount_plan(
            discount_plan_id=discount_plan_id,
            product_id=product_id,
        )

    def list_discount_plans(
        self,
        *,
        product_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        return inventory_data.list_discount_plans(
            product_id=product_id,
            include_inactive=include_inactive,
        )

    # Phase 2: Date range methods
    def get_stock_levels_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return stock levels time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            stock_data = inventory_data.get_stock_levels(date_str)
            for item in stock_data:
                result.append({**item, "date": date_str, "period": date_str})
        return result

    def get_stockout_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return stockout trends time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            stockouts = inventory_data.get_stockout_items(date_str)
            result.append({
                "date": date_str,
                "period": date_str,
                "stockout_count": len(stockouts),
                "items": stockouts
            })
        return result

    def _generate_date_range(
        self, start_date: str, end_date: str, granularity: str
    ) -> list[str]:
        """Generate list of dates between start and end with given granularity."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        dates = []
        current = start

        if granularity == "weekly":
            delta = timedelta(days=7)
        elif granularity == "monthly":
            delta = timedelta(days=30)
        else:  # daily
            delta = timedelta(days=1)

        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += delta

        return dates