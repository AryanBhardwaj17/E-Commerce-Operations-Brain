"""Shared inventory state persistence and product helpers."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeAlias

from core.settings import get_settings
from data.seeds.app_seed_data import get_inventory_seed

CatalogState: TypeAlias = dict[str, list[dict[str, Any]]]

_INVENTORY_SEED = get_inventory_seed()

PRODUCTS = _INVENTORY_SEED["products"]

DEFAULT_CURRENCY = "USD"
DEFAULT_CUSTOM_PRICE = 24.99

STOCKOUT_DATES: dict[str, list[str]] = _INVENTORY_SEED["stockout_dates"]

LOW_STOCK_DATES: dict[str, list[str]] = _INVENTORY_SEED["low_stock_dates"]


def catalog_state_path() -> Path:
    path = get_settings().resolved_runtime_store_dir() / "inventory" / "catalog_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def legacy_custom_products_path() -> Path:
    return get_settings().resolved_runtime_store_dir() / "inventory" / "custom_products.json"


def load_legacy_custom_products() -> list[dict[str, Any]]:
    path = legacy_custom_products_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in payload if isinstance(item, dict)]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def empty_catalog_state() -> CatalogState:
    return {"products": [], "discount_plans": []}


def default_price_for_product(product_id: str) -> float:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return float(product.get("unit_price", DEFAULT_CUSTOM_PRICE))
    return DEFAULT_CUSTOM_PRICE


def normalize_product_record(product: dict[str, Any]) -> dict[str, Any] | None:
    product_id = str(product.get("id") or "").strip().upper()
    product_name = " ".join(str(product.get("name") or "").split()).strip()
    if not product_id or not product_name:
        return None

    normalized: dict[str, Any] = {
        "id": product_id,
        "name": product_name,
        "reorder_point": max(int(product.get("reorder_point", 25)), 1),
        "lead_days": max(int(product.get("lead_days", 5)), 1),
        "unit_price": round(float(product.get("unit_price", default_price_for_product(product_id))), 2),
        "currency": str(product.get("currency", DEFAULT_CURRENCY)).strip().upper() or DEFAULT_CURRENCY,
        "is_deleted": bool(product.get("is_deleted", False)),
    }
    if product.get("quantity_available") is not None:
        normalized["quantity_available"] = max(int(product["quantity_available"]), 0)
    for key in ("created_at", "updated_at", "deleted_at", "source"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    removal_reason = product.get("removal_reason")
    if isinstance(removal_reason, str) and removal_reason.strip():
        normalized["removal_reason"] = removal_reason.strip()
    return normalized


def normalize_discount_plan(plan: dict[str, Any]) -> dict[str, Any] | None:
    discount_plan_id = str(plan.get("discount_plan_id") or "").strip().upper()
    product_id = str(plan.get("product_id") or "").strip().upper()
    if not discount_plan_id or not product_id:
        return None

    normalized: dict[str, Any] = {
        "discount_plan_id": discount_plan_id,
        "product_id": product_id,
        "plan_name": str(plan.get("plan_name") or f"{product_id} Discount").strip(),
        "discount_pct": round(float(plan.get("discount_pct", 0.0)), 2),
        "active": bool(plan.get("active", True)),
        "created_at": str(plan.get("created_at") or utc_now_iso()),
        "updated_at": str(plan.get("updated_at") or plan.get("created_at") or utc_now_iso()),
    }
    for key in ("starts_on", "ends_on", "deactivated_at"):
        value = plan.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def load_catalog_state() -> CatalogState:
    path = catalog_state_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return empty_catalog_state()
        raw_products = payload.get("products", []) if isinstance(payload, dict) else []
        raw_discount_plans = payload.get("discount_plans", []) if isinstance(payload, dict) else []
        products = [
            product
            for product in (
                normalize_product_record(item) for item in raw_products if isinstance(item, dict)
            )
            if product is not None
        ]
        discount_plans = [
            discount_plan
            for discount_plan in (
                normalize_discount_plan(item) for item in raw_discount_plans if isinstance(item, dict)
            )
            if discount_plan is not None
        ]
        return {"products": products, "discount_plans": discount_plans}

    legacy_products = []
    for product in load_legacy_custom_products():
        normalized = normalize_product_record(
            {
                **product,
                "source": product.get("source") or "custom",
                "created_at": product.get("created_at") or utc_now_iso(),
                "updated_at": product.get("updated_at") or product.get("created_at") or utc_now_iso(),
                "unit_price": product.get("unit_price", DEFAULT_CUSTOM_PRICE),
                "currency": product.get("currency", DEFAULT_CURRENCY),
            }
        )
        if normalized is not None:
            legacy_products.append(normalized)
    return {"products": legacy_products, "discount_plans": []}


def save_catalog_state(state: CatalogState) -> None:
    path = catalog_state_path()
    serialized = json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=path.parent,
        prefix=path.stem,
        suffix=".tmp",
    ) as tmp:
        tmp.write(serialized)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def merged_products(
    state: CatalogState | None = None,
    *,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    active_state = state or load_catalog_state()
    products_by_id = {
        product["id"]: normalize_product_record({**product, "source": "base"})
        for product in PRODUCTS
    }
    for product in active_state["products"]:
        normalized = normalize_product_record(product)
        if normalized is None:
            continue
        base = products_by_id.get(normalized["id"], {}) or {}
        products_by_id[normalized["id"]] = {**base, **normalized}

    products = [product for product in products_by_id.values() if product is not None]
    products.sort(key=lambda product: str(product["id"]))
    if include_deleted:
        return products
    return [product for product in products if not bool(product.get("is_deleted", False))]


def validate_iso_date(date_str: str | None) -> str | None:
    if date_str is None:
        return None
    normalized = date_str.strip()
    if not normalized:
        return None
    date.fromisoformat(normalized)
    return normalized


def normalize_product_id(product_id: str) -> str:
    normalized = product_id.strip().upper()
    if not normalized:
        raise ValueError("product_id is required")
    return normalized


def find_product(
    state: CatalogState,
    *,
    product_id: str | None = None,
    product_name: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    products = merged_products(state, include_deleted=include_deleted)
    normalized_product_id = product_id.strip().upper() if isinstance(product_id, str) else None
    normalized_product_name = " ".join(product_name.split()).casefold() if isinstance(product_name, str) else None
    for product in products:
        if normalized_product_id and product["id"].casefold() == normalized_product_id.casefold():
            return product
        if normalized_product_name and product["name"].casefold() == normalized_product_name:
            return product
    return None


def upsert_product(state: CatalogState, product: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_product_record(product)
    if normalized is None:
        raise ValueError("invalid product record")
    for index, existing in enumerate(state["products"]):
        if str(existing.get("id", "")).upper() == normalized["id"]:
            state["products"][index] = normalized
            return normalized
    state["products"].append(normalized)
    state["products"].sort(key=lambda item: str(item.get("id", "")))
    return normalized


def next_custom_sku(existing_products: list[dict[str, Any]]) -> str:
    highest_suffix = 0
    for product in existing_products:
        product_id = str(product.get("id", ""))
        if not product_id.startswith("SKU-CUSTOM-"):
            continue
        try:
            highest_suffix = max(highest_suffix, int(product_id.removeprefix("SKU-CUSTOM-")))
        except ValueError:
            continue
    return f"SKU-CUSTOM-{highest_suffix + 1:03d}"
