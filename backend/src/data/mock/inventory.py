"""Mock inventory catalog and runtime-backed inventory mutations."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from data.mock import inventory_views
from data.mock.inventory_discounts import (
    ensure_no_discount_overlap,
    list_discount_plans_from_state,
    next_discount_plan_id,
    resolve_discount_plan_id,
)
from data.mock.inventory_state import (
    DEFAULT_CURRENCY,
    DEFAULT_CUSTOM_PRICE,
    CatalogState,
    find_product,
    load_catalog_state,
    merged_products,
    next_custom_sku,
    normalize_discount_plan,
    normalize_product_id,
    save_catalog_state,
    upsert_product,
    utc_now_iso,
    validate_iso_date,
)
from data.mock.inventory_views import (
    build_stock_snapshot,
    default_mutable_quantity,
    resolve_quantity,
)


def add_inventory_item(
    product_name: str,
    product_id: str | None = None,
    quantity_available: int = 100,
    reorder_point: int = 25,
    lead_days: int = 5,
) -> dict[str, Any]:
    normalized_name = " ".join(product_name.split()).strip()
    if not normalized_name:
        raise ValueError("product_name is required")

    state = load_catalog_state()
    existing_products = merged_products(state, include_deleted=True)
    normalized_product_id = product_id.strip().upper() if isinstance(product_id, str) and product_id.strip() else None
    existing_product = find_product(
        state,
        product_id=normalized_product_id,
        product_name=normalized_name,
        include_deleted=True,
    )
    if existing_product is not None:
        restored = False
        if existing_product.get("is_deleted"):
            existing_product = upsert_product(
                state,
                {
                    **existing_product,
                    "name": normalized_name,
                    "quantity_available": max(int(quantity_available), 0),
                    "reorder_point": max(int(reorder_point), 1),
                    "lead_days": max(int(lead_days), 1),
                    "is_deleted": False,
                    "deleted_at": "",
                    "removal_reason": "",
                    "updated_at": utc_now_iso(),
                },
            )
            save_catalog_state(state)
            restored = True
        current_date = datetime.now(UTC).date().isoformat()
        snapshot = build_stock_snapshot(
            existing_product,
            resolve_quantity(existing_product, current_date),
            state=state,
            date_str=current_date,
        )
        return {
            "action": "add_inventory_item",
            "status": "executed",
            "result": "restored" if restored else "already_exists",
            "product": snapshot,
            "inventory_count": len(merged_products(state)),
        }

    normalized_reorder_point = max(int(reorder_point), 1)
    normalized_lead_days = max(int(lead_days), 1)
    normalized_quantity = max(int(quantity_available), 0)
    new_product = {
        "id": (normalized_product_id or next_custom_sku(existing_products)).upper(),
        "name": normalized_name,
        "reorder_point": normalized_reorder_point,
        "lead_days": normalized_lead_days,
        "quantity_available": normalized_quantity,
        "unit_price": DEFAULT_CUSTOM_PRICE,
        "currency": DEFAULT_CURRENCY,
        "source": "custom",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "is_deleted": False,
    }
    persisted_product = upsert_product(state, new_product)
    save_catalog_state(state)

    snapshot = build_stock_snapshot(persisted_product, normalized_quantity, state=state)
    return {
        "action": "add_inventory_item",
        "status": "executed",
        "result": "created",
        "product": snapshot,
        "inventory_count": len(merged_products(state)),
    }


def _mutable_product_or_raise(state: CatalogState, product_id: str) -> dict[str, Any]:
    product = find_product(state, product_id=product_id, include_deleted=True)
    if product is None:
        raise ValueError(f"product {product_id.strip().upper()} was not found")
    return product


def increase_inventory_quantity(*, product_id: str, quantity_delta: int) -> dict[str, Any]:
    normalized_product_id = normalize_product_id(product_id)
    normalized_delta = int(quantity_delta)
    if normalized_delta <= 0:
        raise ValueError("quantity_delta must be greater than 0")

    state = load_catalog_state()
    product = _mutable_product_or_raise(state, normalized_product_id)
    if product.get("is_deleted"):
        raise ValueError(f"product {normalized_product_id} has been removed")

    before_quantity = default_mutable_quantity(product)
    after_quantity = before_quantity + normalized_delta
    updated_product = upsert_product(
        state,
        {
            **product,
            "quantity_available": after_quantity,
            "updated_at": utc_now_iso(),
        },
    )
    save_catalog_state(state)

    before_snapshot = build_stock_snapshot(product, before_quantity, state=state)
    after_snapshot = build_stock_snapshot(updated_product, after_quantity, state=state)
    return {
        "action": "increase_inventory_quantity",
        "status": "executed",
        "result": "updated",
        "quantity_delta": normalized_delta,
        "before": before_snapshot,
        "after": after_snapshot,
        "product": after_snapshot,
    }


def decrease_inventory_quantity(*, product_id: str, quantity_delta: int) -> dict[str, Any]:
    normalized_product_id = normalize_product_id(product_id)
    normalized_delta = int(quantity_delta)
    if normalized_delta <= 0:
        raise ValueError("quantity_delta must be greater than 0")

    state = load_catalog_state()
    product = _mutable_product_or_raise(state, normalized_product_id)
    if product.get("is_deleted"):
        raise ValueError(f"product {normalized_product_id} has been removed")

    before_quantity = default_mutable_quantity(product)
    after_quantity = max(before_quantity - normalized_delta, 0)
    updated_product = upsert_product(
        state,
        {
            **product,
            "quantity_available": after_quantity,
            "updated_at": utc_now_iso(),
        },
    )
    save_catalog_state(state)

    before_snapshot = build_stock_snapshot(product, before_quantity, state=state)
    after_snapshot = build_stock_snapshot(updated_product, after_quantity, state=state)
    return {
        "action": "decrease_inventory_quantity",
        "status": "executed",
        "result": "updated",
        "requested_quantity_delta": normalized_delta,
        "applied_quantity_delta": before_quantity - after_quantity,
        "before": before_snapshot,
        "after": after_snapshot,
        "product": after_snapshot,
    }


def remove_inventory_item(*, product_id: str, reason: str = "") -> dict[str, Any]:
    normalized_product_id = normalize_product_id(product_id)
    state = load_catalog_state()
    product = _mutable_product_or_raise(state, normalized_product_id)

    if product.get("is_deleted"):
        snapshot = build_stock_snapshot(
            product,
            int(product.get("quantity_available", 0)),
            state=state,
            include_deleted=True,
        )
        return {
            "action": "remove_inventory_item",
            "status": "executed",
            "result": "already_removed",
            "product": snapshot,
        }

    quantity_available = default_mutable_quantity(product)
    updated_product = upsert_product(
        state,
        {
            **product,
            "quantity_available": quantity_available,
            "is_deleted": True,
            "deleted_at": utc_now_iso(),
            "removal_reason": reason.strip(),
            "updated_at": utc_now_iso(),
        },
    )
    save_catalog_state(state)

    snapshot = build_stock_snapshot(
        updated_product,
        quantity_available,
        state=state,
        include_deleted=True,
    )
    return {
        "action": "remove_inventory_item",
        "status": "executed",
        "result": "removed",
        "product": snapshot,
    }


def update_inventory_price(*, product_id: str, unit_price: float, currency: str = DEFAULT_CURRENCY) -> dict[str, Any]:
    normalized_product_id = normalize_product_id(product_id)
    normalized_price = round(float(unit_price), 2)
    if normalized_price <= 0:
        raise ValueError("unit_price must be greater than 0")

    normalized_currency = str(currency).strip().upper() or DEFAULT_CURRENCY
    state = load_catalog_state()
    product = _mutable_product_or_raise(state, normalized_product_id)
    if product.get("is_deleted"):
        raise ValueError(f"product {normalized_product_id} has been removed")

    quantity_available = default_mutable_quantity(product)
    before_snapshot = build_stock_snapshot(product, quantity_available, state=state)
    updated_product = upsert_product(
        state,
        {
            **product,
            "unit_price": normalized_price,
            "currency": normalized_currency,
            "updated_at": utc_now_iso(),
        },
    )
    save_catalog_state(state)
    after_snapshot = build_stock_snapshot(updated_product, quantity_available, state=state)
    return {
        "action": "update_inventory_price",
        "status": "executed",
        "result": "updated",
        "before": before_snapshot,
        "after": after_snapshot,
        "product": after_snapshot,
    }


def create_discount_plan(
    *,
    product_id: str,
    discount_pct: float,
    plan_name: str | None = None,
    starts_on: str | None = None,
    ends_on: str | None = None,
) -> dict[str, Any]:
    normalized_product_id = normalize_product_id(product_id)
    normalized_discount_pct = round(float(discount_pct), 2)
    if normalized_discount_pct <= 0 or normalized_discount_pct >= 100:
        raise ValueError("discount_pct must be greater than 0 and less than 100")

    normalized_starts_on = validate_iso_date(starts_on)
    normalized_ends_on = validate_iso_date(ends_on)
    if normalized_starts_on and normalized_ends_on and normalized_starts_on > normalized_ends_on:
        raise ValueError("starts_on must be on or before ends_on")

    state = load_catalog_state()
    product = _mutable_product_or_raise(state, normalized_product_id)
    if product.get("is_deleted"):
        raise ValueError(f"product {normalized_product_id} has been removed")

    ensure_no_discount_overlap(
        state,
        product_id=normalized_product_id,
        starts_on=normalized_starts_on,
        ends_on=normalized_ends_on,
    )
    discount_plan = {
        "discount_plan_id": next_discount_plan_id(state),
        "product_id": normalized_product_id,
        "plan_name": (plan_name or f"{normalized_discount_pct:.0f}% off {product['name']}").strip(),
        "discount_pct": normalized_discount_pct,
        "starts_on": normalized_starts_on,
        "ends_on": normalized_ends_on,
        "active": True,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    normalized_plan = normalize_discount_plan(discount_plan)
    if normalized_plan is None:
        raise ValueError("invalid discount plan")

    state["discount_plans"].append(normalized_plan)
    state["discount_plans"].sort(key=lambda item: str(item.get("discount_plan_id", "")))
    save_catalog_state(state)

    quantity_available = default_mutable_quantity(product)
    snapshot = build_stock_snapshot(product, quantity_available, state=state)
    return {
        "action": "create_discount_plan",
        "status": "executed",
        "result": "created",
        "discount_plan": normalized_plan,
        "product": snapshot,
    }


def update_discount_plan(
    *,
    discount_plan_id: str | None = None,
    product_id: str | None = None,
    discount_pct: float | None = None,
    plan_name: str | None = None,
    starts_on: str | None = None,
    ends_on: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    state = load_catalog_state()
    normalized_discount_plan_id = resolve_discount_plan_id(
        state,
        discount_plan_id=discount_plan_id,
        product_id=product_id,
    )
    plan_index = next(
        (
            index
            for index, plan in enumerate(state["discount_plans"])
            if str(plan.get("discount_plan_id", "")).upper() == normalized_discount_plan_id
        ),
        None,
    )
    if plan_index is None:
        raise ValueError(f"discount plan {normalized_discount_plan_id} was not found")

    existing_plan = state["discount_plans"][plan_index]
    normalized_starts_on = validate_iso_date(starts_on) if starts_on is not None else existing_plan.get("starts_on")
    normalized_ends_on = validate_iso_date(ends_on) if ends_on is not None else existing_plan.get("ends_on")
    if normalized_starts_on and normalized_ends_on and normalized_starts_on > normalized_ends_on:
        raise ValueError("starts_on must be on or before ends_on")

    normalized_discount_pct = (
        round(float(discount_pct), 2) if discount_pct is not None else float(existing_plan["discount_pct"])
    )
    if normalized_discount_pct <= 0 or normalized_discount_pct >= 100:
        raise ValueError("discount_pct must be greater than 0 and less than 100")

    normalized_active = bool(active) if active is not None else bool(existing_plan.get("active", True))
    if normalized_active:
        ensure_no_discount_overlap(
            state,
            product_id=str(existing_plan["product_id"]),
            starts_on=normalized_starts_on,
            ends_on=normalized_ends_on,
            ignore_discount_plan_id=normalized_discount_plan_id,
        )

    updated_plan = normalize_discount_plan(
        {
            **existing_plan,
            "discount_pct": normalized_discount_pct,
            "plan_name": (plan_name or existing_plan.get("plan_name") or "Discount").strip(),
            "starts_on": normalized_starts_on,
            "ends_on": normalized_ends_on,
            "active": normalized_active,
            "deactivated_at": utc_now_iso() if active is False else existing_plan.get("deactivated_at"),
            "updated_at": utc_now_iso(),
        }
    )
    if updated_plan is None:
        raise ValueError("invalid discount plan")
    state["discount_plans"][plan_index] = updated_plan
    save_catalog_state(state)

    return {
        "action": "update_discount_plan",
        "status": "executed",
        "result": "updated",
        "discount_plan": updated_plan,
    }


def deactivate_discount_plan(
    *,
    discount_plan_id: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    return update_discount_plan(
        discount_plan_id=discount_plan_id,
        product_id=product_id,
        active=False,
    )


def list_discount_plans(*, product_id: str | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
    state = load_catalog_state()
    return list_discount_plans_from_state(
        state,
        product_id=product_id,
        include_inactive=include_inactive,
    )


def get_stock_levels(date_str: str) -> list[dict[str, Any]]:
    return inventory_views.get_stock_levels(date_str)


def get_stockout_items(date_str: str) -> list[dict[str, Any]]:
    return inventory_views.get_stockout_items(date_str)


def get_low_stock_alerts(date_str: str) -> list[dict[str, Any]]:
    return inventory_views.get_low_stock_alerts(date_str)


def get_conversion_impact(date_str: str) -> dict[str, Any]:
    return inventory_views.get_conversion_impact(date_str)
