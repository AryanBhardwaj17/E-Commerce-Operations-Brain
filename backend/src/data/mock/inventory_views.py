"""Shared inventory stock-view helpers."""
from __future__ import annotations

import random
from datetime import date
from typing import Any

from data.mock.inventory_discounts import select_active_discount_plan
from data.mock.inventory_state import (
    DEFAULT_CURRENCY,
    LOW_STOCK_DATES,
    STOCKOUT_DATES,
    CatalogState,
    default_price_for_product,
    load_catalog_state,
    merged_products,
)


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xBEEF)


def resolve_quantity(product: dict[str, Any], date_str: str) -> int:
    if product.get("quantity_available") is not None:
        return max(int(product["quantity_available"]), 0)

    stockouts = set(STOCKOUT_DATES.get(date_str, []))
    low_stock = set(LOW_STOCK_DATES.get(date_str, []))
    rng = _seed(date.fromisoformat(date_str))
    reorder_point = int(product["reorder_point"])

    if product["id"] in stockouts:
        return 0
    if product["id"] in low_stock:
        return rng.randint(5, reorder_point - 1)
    return rng.randint(reorder_point + 10, reorder_point * 4)


def default_mutable_quantity(product: dict[str, Any]) -> int:
    if product.get("quantity_available") is not None:
        return max(int(product["quantity_available"]), 0)
    reorder_point = max(int(product.get("reorder_point", 25)), 1)
    return max(reorder_point * 2, reorder_point + 10)


def build_stock_snapshot(
    product: dict[str, Any],
    quantity_available: int,
    *,
    state: CatalogState | None = None,
    date_str: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    reorder_point = int(product["reorder_point"])
    quantity = max(int(quantity_available), 0)
    is_deleted = bool(product.get("is_deleted", False))
    active_state = state or load_catalog_state()
    active_discount = select_active_discount_plan(active_state, product["id"], date_str=date_str)
    unit_price = round(float(product.get("unit_price", default_price_for_product(product["id"]))), 2)
    effective_price = (
        round(unit_price * (100.0 - float(active_discount["discount_pct"])) / 100.0, 2)
        if active_discount is not None
        else unit_price
    )
    return {
        "product_id": product["id"],
        "product_name": product["name"],
        "quantity_available": quantity,
        "reorder_point": reorder_point,
        "status": (
            "removed"
            if is_deleted and include_deleted
            else "stockout"
            if quantity == 0
            else "low"
            if quantity < reorder_point
            else "healthy"
        ),
        "days_until_stockout": (
            None
            if is_deleted and include_deleted
            else 0
            if quantity == 0
            else round(quantity / max(reorder_point / 10, 1), 1)
        ),
        "unit_price": unit_price,
        "currency": str(product.get("currency", DEFAULT_CURRENCY)).upper(),
        "effective_price": effective_price,
        "active_discount": active_discount,
        "is_deleted": is_deleted,
    }


def get_stock_levels(date_str: str) -> list[dict[str, Any]]:
    state = load_catalog_state()
    return [
        build_stock_snapshot(product, resolve_quantity(product, date_str), state=state, date_str=date_str)
        for product in merged_products(state)
    ]


def get_stockout_items(date_str: str) -> list[dict[str, Any]]:
    levels = get_stock_levels(date_str)
    return [item for item in levels if item["status"] == "stockout"]


def get_low_stock_alerts(date_str: str) -> list[dict[str, Any]]:
    levels = get_stock_levels(date_str)
    return [item for item in levels if item["status"] in ("stockout", "low")]


def get_conversion_impact(date_str: str) -> dict[str, Any]:
    stockouts = get_stockout_items(date_str)
    stockout_ids = {stockout["product_id"] for stockout in stockouts}

    estimated_daily_revenue = 59000.0
    lost_revenue_estimate = len(stockout_ids) * estimated_daily_revenue * 0.10

    return {
        "date": date_str,
        "stockout_product_count": len(stockout_ids),
        "stockout_products": list(stockout_ids),
        "estimated_lost_revenue": round(lost_revenue_estimate, 2),
        "estimated_lost_orders": len(stockout_ids) * 45,
        "conversion_impact_pct": round(len(stockout_ids) * 3.5, 1),
    }
