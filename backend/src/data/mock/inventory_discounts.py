"""Shared inventory discount-plan helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

from data.mock.inventory_state import CatalogState, load_catalog_state, normalize_product_id


def next_discount_plan_id(state: CatalogState) -> str:
    highest_suffix = 0
    for plan in state["discount_plans"]:
        plan_id = str(plan.get("discount_plan_id", ""))
        if not plan_id.startswith("DISC-"):
            continue
        try:
            highest_suffix = max(highest_suffix, int(plan_id.removeprefix("DISC-")))
        except ValueError:
            continue
    return f"DISC-{highest_suffix + 1:03d}"


def product_discount_plans(
    state: CatalogState,
    product_id: str,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    normalized_product_id = normalize_product_id(product_id)
    discount_plans = [
        plan
        for plan in state["discount_plans"]
        if plan.get("product_id") == normalized_product_id
        and (include_inactive or bool(plan.get("active", True)))
    ]
    discount_plans.sort(key=lambda plan: str(plan.get("discount_plan_id", "")))
    return discount_plans


def resolve_discount_plan_id(
    state: CatalogState,
    *,
    discount_plan_id: str | None = None,
    product_id: str | None = None,
) -> str:
    if isinstance(discount_plan_id, str) and discount_plan_id.strip():
        return discount_plan_id.strip().upper()

    if isinstance(product_id, str) and product_id.strip():
        normalized_product_id = normalize_product_id(product_id)
        active_plans = product_discount_plans(state, normalized_product_id, include_inactive=False)
        if not active_plans:
            raise ValueError(f"no active discount plan found for {normalized_product_id}")
        if len(active_plans) > 1:
            raise ValueError(
                f"multiple active discount plans exist for {normalized_product_id}; specify discount_plan_id"
            )
        return str(active_plans[0]["discount_plan_id"]).upper()

    raise ValueError("discount_plan_id or product_id is required")


def date_range_overlaps(
    starts_on: str | None,
    ends_on: str | None,
    other_starts_on: str | None,
    other_ends_on: str | None,
) -> bool:
    starts = date.min if starts_on is None else date.fromisoformat(starts_on)
    ends = date.max if ends_on is None else date.fromisoformat(ends_on)
    other_starts = date.min if other_starts_on is None else date.fromisoformat(other_starts_on)
    other_ends = date.max if other_ends_on is None else date.fromisoformat(other_ends_on)
    return starts <= other_ends and other_starts <= ends


def ensure_no_discount_overlap(
    state: CatalogState,
    *,
    product_id: str,
    starts_on: str | None,
    ends_on: str | None,
    ignore_discount_plan_id: str | None = None,
) -> None:
    normalized_product_id = normalize_product_id(product_id)
    ignored_plan_id = ignore_discount_plan_id.strip().upper() if isinstance(ignore_discount_plan_id, str) else None
    for plan in product_discount_plans(state, normalized_product_id, include_inactive=False):
        plan_id = str(plan.get("discount_plan_id", "")).upper()
        if ignored_plan_id and plan_id == ignored_plan_id:
            continue
        if date_range_overlaps(starts_on, ends_on, plan.get("starts_on"), plan.get("ends_on")):
            raise ValueError(
                f"discount plan {plan_id} already overlaps the requested date range for {normalized_product_id}"
            )


def select_active_discount_plan(
    state: CatalogState,
    product_id: str,
    *,
    date_str: str | None = None,
) -> dict[str, Any] | None:
    effective_date = date.today() if date_str is None else date.fromisoformat(date_str)
    candidates = []
    for plan in product_discount_plans(state, product_id, include_inactive=False):
        starts_on = plan.get("starts_on")
        ends_on = plan.get("ends_on")
        if starts_on and effective_date < date.fromisoformat(starts_on):
            continue
        if ends_on and effective_date > date.fromisoformat(ends_on):
            continue
        candidates.append(plan)
    if not candidates:
        return None
    candidates.sort(key=lambda plan: float(plan.get("discount_pct", 0.0)), reverse=True)
    selected = candidates[0]
    return {
        "discount_plan_id": selected["discount_plan_id"],
        "product_id": selected["product_id"],
        "plan_name": selected["plan_name"],
        "discount_pct": float(selected["discount_pct"]),
        "starts_on": selected.get("starts_on"),
        "ends_on": selected.get("ends_on"),
    }


def list_discount_plans_from_state(
    state: CatalogState,
    *,
    product_id: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    plans = state["discount_plans"]
    if product_id is not None:
        normalized_product_id = normalize_product_id(product_id)
        plans = [plan for plan in plans if str(plan.get("product_id", "")).upper() == normalized_product_id]
    if not include_inactive:
        plans = [plan for plan in plans if bool(plan.get("active", True))]
    plans.sort(key=lambda plan: str(plan.get("discount_plan_id", "")))
    return plans


def list_discount_plans_snapshot(
    *,
    product_id: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    state = load_catalog_state()
    return list_discount_plans_from_state(
        state,
        product_id=product_id,
        include_inactive=include_inactive,
    )
