"""Postgres inventory repository adapter."""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase

DEFAULT_CURRENCY = "USD"
DEFAULT_CUSTOM_PRICE = 24.99


def _generate_date_range(start_date: str, end_date: str, granularity: str) -> list[str]:
    """Generate list of dates between start and end with given granularity."""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    if granularity == "weekly":
        delta = timedelta(days=7)
    elif granularity == "monthly":
        delta = timedelta(days=30)
    else:  # daily
        delta = timedelta(days=1)

    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += delta
    return dates


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xBEEF)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _serialize_date(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_product_id(product_id: str) -> str:
    normalized = product_id.strip().upper()
    if not normalized:
        raise ValueError("product_id is required")
    return normalized


def _validate_iso_date(date_str: str | None) -> str | None:
    if date_str is None:
        return None
    normalized = date_str.strip()
    if not normalized:
        return None
    date.fromisoformat(normalized)
    return normalized


def _date_range_overlaps(
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


def _product_discount_plans(
    state: dict[str, list[dict[str, Any]]],
    product_id: str,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    normalized_product_id = _normalize_product_id(product_id)
    plans = [
        plan
        for plan in state["discount_plans"]
        if str(plan.get("product_id", "")).upper() == normalized_product_id
        and (include_inactive or bool(plan.get("active", True)))
    ]
    plans.sort(key=lambda plan: str(plan.get("discount_plan_id", "")))
    return plans


def _resolve_discount_plan_id(
    state: dict[str, list[dict[str, Any]]],
    *,
    discount_plan_id: str | None = None,
    product_id: str | None = None,
) -> str:
    if isinstance(discount_plan_id, str) and discount_plan_id.strip():
        return discount_plan_id.strip().upper()

    if isinstance(product_id, str) and product_id.strip():
        normalized_product_id = _normalize_product_id(product_id)
        active_plans = _product_discount_plans(state, normalized_product_id, include_inactive=False)
        if not active_plans:
            raise ValueError(f"no active discount plan found for {normalized_product_id}")
        if len(active_plans) > 1:
            raise ValueError(
                f"multiple active discount plans exist for {normalized_product_id}; specify discount_plan_id"
            )
        return str(active_plans[0]["discount_plan_id"]).upper()

    raise ValueError("discount_plan_id or product_id is required")


def _ensure_no_discount_overlap(
    state: dict[str, list[dict[str, Any]]],
    *,
    product_id: str,
    starts_on: str | None,
    ends_on: str | None,
    ignore_discount_plan_id: str | None = None,
) -> None:
    normalized_product_id = _normalize_product_id(product_id)
    ignored_plan_id = ignore_discount_plan_id.strip().upper() if isinstance(ignore_discount_plan_id, str) else None
    for plan in _product_discount_plans(state, normalized_product_id, include_inactive=False):
        plan_id = str(plan.get("discount_plan_id", "")).upper()
        if ignored_plan_id and plan_id == ignored_plan_id:
            continue
        if _date_range_overlaps(starts_on, ends_on, plan.get("starts_on"), plan.get("ends_on")):
            raise ValueError(
                f"discount plan {plan_id} already overlaps the requested date range for {normalized_product_id}"
            )


def _find_product(
    products: list[dict[str, Any]],
    *,
    product_id: str | None = None,
    product_name: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    normalized_product_id = product_id.strip().upper() if isinstance(product_id, str) else None
    normalized_product_name = " ".join(product_name.split()).casefold() if isinstance(product_name, str) else None
    for product in products:
        if not include_deleted and bool(product.get("is_deleted", False)):
            continue
        if normalized_product_id and str(product["id"]).casefold() == normalized_product_id.casefold():
            return product
        if normalized_product_name and str(product["name"]).casefold() == normalized_product_name:
            return product
    return None


def _select_active_discount_plan(
    state: dict[str, list[dict[str, Any]]],
    product_id: str,
    *,
    date_str: str | None = None,
) -> dict[str, Any] | None:
    effective_date = date.fromisoformat(date_str) if date_str else datetime.now(UTC).date()
    candidates = []
    for plan in _product_discount_plans(state, product_id, include_inactive=False):
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


def _resolve_quantity(product: dict[str, Any], date_str: str, status_overrides: dict[str, str]) -> int:
    if product.get("quantity_available") is not None:
        return max(int(product["quantity_available"]), 0)

    status = status_overrides.get(str(product["id"]))
    rng = _seed(date.fromisoformat(date_str))
    reorder_point = int(product["reorder_point"])

    if status == "stockout":
        return 0
    if status == "low":
        return rng.randint(5, reorder_point - 1)
    return rng.randint(reorder_point + 10, reorder_point * 4)


def _default_mutable_quantity(product: dict[str, Any]) -> int:
    if product.get("quantity_available") is not None:
        return max(int(product["quantity_available"]), 0)
    reorder_point = max(int(product.get("reorder_point", 25)), 1)
    return max(reorder_point * 2, reorder_point + 10)


def _build_stock_snapshot(
    product: dict[str, Any],
    quantity_available: int,
    *,
    state: dict[str, list[dict[str, Any]]],
    date_str: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    reorder_point = int(product["reorder_point"])
    quantity = max(int(quantity_available), 0)
    is_deleted = bool(product.get("is_deleted", False))
    active_discount = _select_active_discount_plan(state, str(product["id"]), date_str=date_str)
    unit_price = round(float(product.get("unit_price", DEFAULT_CUSTOM_PRICE)), 2)
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


def _next_custom_sku(products: list[dict[str, Any]]) -> str:
    highest_suffix = 0
    for product in products:
        product_id = str(product.get("id", ""))
        if not product_id.startswith("SKU-CUSTOM-"):
            continue
        try:
            highest_suffix = max(highest_suffix, int(product_id.removeprefix("SKU-CUSTOM-")))
        except ValueError:
            continue
    return f"SKU-CUSTOM-{highest_suffix + 1:03d}"


def _next_discount_plan_id(state: dict[str, list[dict[str, Any]]]) -> str:
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


class PostgresInventoryRepository:
    def __init__(self, database: PostgresRepositoryDatabase) -> None:
        self.database = database

    def _load_products(self, connection: Any, *, include_deleted: bool = True) -> list[dict[str, Any]]:
        query = f"""
            SELECT product_id AS id,
                   product_name AS name,
                   reorder_point,
                   lead_days,
                   unit_price::float8 AS unit_price,
                   currency,
                   quantity_available,
                   source,
                   created_at,
                   updated_at,
                   is_deleted,
                   deleted_at,
                   removal_reason
            FROM {self.database.qualified('products')}
        """
        if not include_deleted:
            query += " WHERE is_deleted = FALSE"
        query += " ORDER BY product_id"
        rows = connection.execute(query).fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "reorder_point": int(row["reorder_point"]),
                "lead_days": int(row["lead_days"]),
                "unit_price": round(float(row["unit_price"]), 2),
                "currency": str(row["currency"]),
                "quantity_available": int(row["quantity_available"]) if row["quantity_available"] is not None else None,
                "source": str(row["source"]) if row["source"] else "base",
                "created_at": _serialize_datetime(row["created_at"]),
                "updated_at": _serialize_datetime(row["updated_at"]),
                "is_deleted": bool(row["is_deleted"]),
                "deleted_at": _serialize_datetime(row["deleted_at"]),
                "removal_reason": str(row["removal_reason"] or ""),
            }
            for row in rows
        ]

    def _load_discount_plans(self, connection: Any) -> list[dict[str, Any]]:
        rows = connection.execute(
            f"""
            SELECT discount_plan_id, product_id, plan_name,
                   discount_pct::float8 AS discount_pct,
                   starts_on, ends_on, active,
                   created_at, updated_at, deactivated_at
            FROM {self.database.qualified('inventory_discount_plans')}
            ORDER BY discount_plan_id
            """
        ).fetchall()
        return [
            {
                "discount_plan_id": str(row["discount_plan_id"]),
                "product_id": str(row["product_id"]),
                "plan_name": str(row["plan_name"]),
                "discount_pct": round(float(row["discount_pct"]), 2),
                "starts_on": _serialize_date(row["starts_on"]),
                "ends_on": _serialize_date(row["ends_on"]),
                "active": bool(row["active"]),
                "created_at": _serialize_datetime(row["created_at"]),
                "updated_at": _serialize_datetime(row["updated_at"]),
                "deactivated_at": _serialize_datetime(row["deactivated_at"]),
            }
            for row in rows
        ]

    def _load_state(self, connection: Any) -> dict[str, list[dict[str, Any]]]:
        return {
            "products": self._load_products(connection, include_deleted=True),
            "discount_plans": self._load_discount_plans(connection),
        }

    def _status_overrides_for_date(self, connection: Any, date_str: str) -> dict[str, str]:
        rows = connection.execute(
            f"SELECT product_id, status FROM {self.database.qualified('inventory_status_overrides')} WHERE effective_date = %s",
            (date.fromisoformat(date_str),),
        ).fetchall()
        return {str(row["product_id"]): str(row["status"]) for row in rows}

    def _upsert_product(self, connection: Any, product: dict[str, Any]) -> None:
        connection.execute(
            f"""
            INSERT INTO {self.database.qualified('products')} (
                product_id,
                product_name,
                reorder_point,
                lead_days,
                unit_price,
                currency,
                quantity_available,
                source,
                created_at,
                updated_at,
                is_deleted,
                deleted_at,
                removal_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id) DO UPDATE
            SET product_name = EXCLUDED.product_name,
                reorder_point = EXCLUDED.reorder_point,
                lead_days = EXCLUDED.lead_days,
                unit_price = EXCLUDED.unit_price,
                currency = EXCLUDED.currency,
                quantity_available = EXCLUDED.quantity_available,
                source = EXCLUDED.source,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                is_deleted = EXCLUDED.is_deleted,
                deleted_at = EXCLUDED.deleted_at,
                removal_reason = EXCLUDED.removal_reason
            """,
            (
                product["id"],
                product["name"],
                int(product["reorder_point"]),
                int(product["lead_days"]),
                round(float(product["unit_price"]), 2),
                str(product.get("currency", DEFAULT_CURRENCY)).upper(),
                product.get("quantity_available"),
                str(product.get("source") or "base"),
                product.get("created_at"),
                product.get("updated_at"),
                bool(product.get("is_deleted", False)),
                product.get("deleted_at"),
                str(product.get("removal_reason") or ""),
            ),
        )

    def add_inventory_item(
        self,
        *,
        product_name: str,
        product_id: str | None = None,
        quantity_available: int = 100,
        reorder_point: int = 25,
        lead_days: int = 5,
    ) -> dict[str, Any]:
        normalized_name = " ".join(product_name.split()).strip()
        if not normalized_name:
            raise ValueError("product_name is required")

        normalized_product_id = product_id.strip().upper() if isinstance(product_id, str) and product_id.strip() else None
        normalized_quantity = max(int(quantity_available), 0)
        normalized_reorder_point = max(int(reorder_point), 1)
        normalized_lead_days = max(int(lead_days), 1)
        now = _utc_now()
        today = now.date().isoformat()

        with self.database.connection() as connection:
            state = self._load_state(connection)
            products = state["products"]
            existing_product = _find_product(
                products,
                product_id=normalized_product_id,
                product_name=normalized_name,
                include_deleted=True,
            )

            if existing_product is not None:
                restored = False
                if existing_product.get("is_deleted"):
                    updated_product = {
                        **existing_product,
                        "name": normalized_name,
                        "quantity_available": normalized_quantity,
                        "reorder_point": normalized_reorder_point,
                        "lead_days": normalized_lead_days,
                        "is_deleted": False,
                        "deleted_at": None,
                        "removal_reason": "",
                        "updated_at": now,
                    }
                    self._upsert_product(connection, updated_product)
                    state = self._load_state(connection)
                    existing_product = _find_product(
                        state["products"],
                        product_id=str(updated_product["id"]),
                        include_deleted=True,
                    )
                    restored = True

                if existing_product is None:
                    raise ValueError("unable to restore existing product")

                status_overrides = self._status_overrides_for_date(connection, today)
                snapshot = _build_stock_snapshot(
                    existing_product,
                    _resolve_quantity(existing_product, today, status_overrides),
                    state=state,
                    date_str=today,
                )
                return {
                    "action": "add_inventory_item",
                    "status": "executed",
                    "result": "restored" if restored else "already_exists",
                    "product": snapshot,
                    "inventory_count": len([product for product in state["products"] if not product.get("is_deleted")]),
                }

            new_product = {
                "id": (normalized_product_id or _next_custom_sku(products)).upper(),
                "name": normalized_name,
                "reorder_point": normalized_reorder_point,
                "lead_days": normalized_lead_days,
                "quantity_available": normalized_quantity,
                "unit_price": DEFAULT_CUSTOM_PRICE,
                "currency": DEFAULT_CURRENCY,
                "source": "custom",
                "created_at": now,
                "updated_at": now,
                "is_deleted": False,
                "deleted_at": None,
                "removal_reason": "",
            }
            self._upsert_product(connection, new_product)
            state = self._load_state(connection)
            persisted_product = _find_product(state["products"], product_id=str(new_product["id"]), include_deleted=True)
            if persisted_product is None:
                raise ValueError("unable to persist inventory product")
            snapshot = _build_stock_snapshot(persisted_product, normalized_quantity, state=state, date_str=today)
            return {
                "action": "add_inventory_item",
                "status": "executed",
                "result": "created",
                "product": snapshot,
                "inventory_count": len([product for product in state["products"] if not product.get("is_deleted")]),
            }

    def _mutable_product_or_raise(self, products: list[dict[str, Any]], product_id: str) -> dict[str, Any]:
        product = _find_product(products, product_id=product_id, include_deleted=True)
        if product is None:
            raise ValueError(f"product {product_id.strip().upper()} was not found")
        return product

    def increase_inventory_quantity(self, *, product_id: str, quantity_delta: int) -> dict[str, Any]:
        normalized_product_id = _normalize_product_id(product_id)
        normalized_delta = int(quantity_delta)
        if normalized_delta <= 0:
            raise ValueError("quantity_delta must be greater than 0")

        with self.database.connection() as connection:
            state = self._load_state(connection)
            product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            if product.get("is_deleted"):
                raise ValueError(f"product {normalized_product_id} has been removed")

            before_quantity = _default_mutable_quantity(product)
            after_quantity = before_quantity + normalized_delta
            updated_product = {**product, "quantity_available": after_quantity, "updated_at": _utc_now()}
            self._upsert_product(connection, updated_product)

            state = self._load_state(connection)
            persisted_product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            before_snapshot = _build_stock_snapshot(product, before_quantity, state=state)
            after_snapshot = _build_stock_snapshot(persisted_product, after_quantity, state=state)
            return {
                "action": "increase_inventory_quantity",
                "status": "executed",
                "result": "updated",
                "quantity_delta": normalized_delta,
                "before": before_snapshot,
                "after": after_snapshot,
                "product": after_snapshot,
            }

    def decrease_inventory_quantity(self, *, product_id: str, quantity_delta: int) -> dict[str, Any]:
        normalized_product_id = _normalize_product_id(product_id)
        normalized_delta = int(quantity_delta)
        if normalized_delta <= 0:
            raise ValueError("quantity_delta must be greater than 0")

        with self.database.connection() as connection:
            state = self._load_state(connection)
            product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            if product.get("is_deleted"):
                raise ValueError(f"product {normalized_product_id} has been removed")

            before_quantity = _default_mutable_quantity(product)
            after_quantity = max(before_quantity - normalized_delta, 0)
            updated_product = {**product, "quantity_available": after_quantity, "updated_at": _utc_now()}
            self._upsert_product(connection, updated_product)

            state = self._load_state(connection)
            persisted_product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            before_snapshot = _build_stock_snapshot(product, before_quantity, state=state)
            after_snapshot = _build_stock_snapshot(persisted_product, after_quantity, state=state)
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

    def remove_inventory_item(self, *, product_id: str, reason: str = "") -> dict[str, Any]:
        normalized_product_id = _normalize_product_id(product_id)
        with self.database.connection() as connection:
            state = self._load_state(connection)
            product = self._mutable_product_or_raise(state["products"], normalized_product_id)

            if product.get("is_deleted"):
                snapshot = _build_stock_snapshot(
                    product,
                    int(product.get("quantity_available") or 0),
                    state=state,
                    include_deleted=True,
                )
                return {
                    "action": "remove_inventory_item",
                    "status": "executed",
                    "result": "already_removed",
                    "product": snapshot,
                }

            quantity_available = _default_mutable_quantity(product)
            updated_product = {
                **product,
                "quantity_available": quantity_available,
                "is_deleted": True,
                "deleted_at": _utc_now(),
                "removal_reason": reason.strip(),
                "updated_at": _utc_now(),
            }
            self._upsert_product(connection, updated_product)

            state = self._load_state(connection)
            persisted_product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            snapshot = _build_stock_snapshot(
                persisted_product,
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

    def update_inventory_price(self, *, product_id: str, unit_price: float, currency: str = DEFAULT_CURRENCY) -> dict[str, Any]:
        normalized_product_id = _normalize_product_id(product_id)
        normalized_price = round(float(unit_price), 2)
        if normalized_price <= 0:
            raise ValueError("unit_price must be greater than 0")

        normalized_currency = str(currency).strip().upper() or DEFAULT_CURRENCY
        with self.database.connection() as connection:
            state = self._load_state(connection)
            product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            if product.get("is_deleted"):
                raise ValueError(f"product {normalized_product_id} has been removed")

            quantity_available = _default_mutable_quantity(product)
            before_snapshot = _build_stock_snapshot(product, quantity_available, state=state)
            updated_product = {
                **product,
                "unit_price": normalized_price,
                "currency": normalized_currency,
                "updated_at": _utc_now(),
            }
            self._upsert_product(connection, updated_product)

            state = self._load_state(connection)
            persisted_product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            after_snapshot = _build_stock_snapshot(persisted_product, quantity_available, state=state)
            return {
                "action": "update_inventory_price",
                "status": "executed",
                "result": "updated",
                "before": before_snapshot,
                "after": after_snapshot,
                "product": after_snapshot,
            }

    def create_discount_plan(
        self,
        *,
        product_id: str,
        discount_pct: float,
        plan_name: str | None = None,
        starts_on: str | None = None,
        ends_on: str | None = None,
    ) -> dict[str, Any]:
        normalized_product_id = _normalize_product_id(product_id)
        normalized_discount_pct = round(float(discount_pct), 2)
        if normalized_discount_pct <= 0 or normalized_discount_pct >= 100:
            raise ValueError("discount_pct must be greater than 0 and less than 100")

        normalized_starts_on = _validate_iso_date(starts_on)
        normalized_ends_on = _validate_iso_date(ends_on)
        if normalized_starts_on and normalized_ends_on and normalized_starts_on > normalized_ends_on:
            raise ValueError("starts_on must be on or before ends_on")

        with self.database.connection() as connection:
            state = self._load_state(connection)
            product = self._mutable_product_or_raise(state["products"], normalized_product_id)
            if product.get("is_deleted"):
                raise ValueError(f"product {normalized_product_id} has been removed")

            _ensure_no_discount_overlap(
                state,
                product_id=normalized_product_id,
                starts_on=normalized_starts_on,
                ends_on=normalized_ends_on,
            )
            now = _utc_now()
            discount_plan = {
                "discount_plan_id": _next_discount_plan_id(state),
                "product_id": normalized_product_id,
                "plan_name": (plan_name or f"{normalized_discount_pct:.0f}% off {product['name']}").strip(),
                "discount_pct": normalized_discount_pct,
                "starts_on": normalized_starts_on,
                "ends_on": normalized_ends_on,
                "active": True,
                "created_at": now,
                "updated_at": now,
                "deactivated_at": None,
            }
            connection.execute(
                f"""
                INSERT INTO {self.database.qualified('inventory_discount_plans')} (
                    discount_plan_id,
                    product_id,
                    plan_name,
                    discount_pct,
                    starts_on,
                    ends_on,
                    active,
                    created_at,
                    updated_at,
                    deactivated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    discount_plan["discount_plan_id"],
                    discount_plan["product_id"],
                    discount_plan["plan_name"],
                    discount_plan["discount_pct"],
                    discount_plan["starts_on"],
                    discount_plan["ends_on"],
                    discount_plan["active"],
                    discount_plan["created_at"],
                    discount_plan["updated_at"],
                    discount_plan["deactivated_at"],
                ),
            )
            state = self._load_state(connection)
            quantity_available = _default_mutable_quantity(product)
            snapshot = _build_stock_snapshot(product, quantity_available, state=state)
            persisted_plan = next(
                plan for plan in state["discount_plans"] if plan["discount_plan_id"] == discount_plan["discount_plan_id"]
            )
            return {
                "action": "create_discount_plan",
                "status": "executed",
                "result": "created",
                "discount_plan": persisted_plan,
                "product": snapshot,
            }

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
        with self.database.connection() as connection:
            state = self._load_state(connection)
            normalized_discount_plan_id = _resolve_discount_plan_id(
                state,
                discount_plan_id=discount_plan_id,
                product_id=product_id,
            )
            existing_plan = next(
                (
                    plan
                    for plan in state["discount_plans"]
                    if str(plan.get("discount_plan_id", "")).upper() == normalized_discount_plan_id
                ),
                None,
            )
            if existing_plan is None:
                raise ValueError(f"discount plan {normalized_discount_plan_id} was not found")

            normalized_starts_on = _validate_iso_date(starts_on) if starts_on is not None else existing_plan.get("starts_on")
            normalized_ends_on = _validate_iso_date(ends_on) if ends_on is not None else existing_plan.get("ends_on")
            if normalized_starts_on and normalized_ends_on and normalized_starts_on > normalized_ends_on:
                raise ValueError("starts_on must be on or before ends_on")

            normalized_discount_pct = (
                round(float(discount_pct), 2) if discount_pct is not None else float(existing_plan["discount_pct"])
            )
            if normalized_discount_pct <= 0 or normalized_discount_pct >= 100:
                raise ValueError("discount_pct must be greater than 0 and less than 100")

            normalized_active = bool(active) if active is not None else bool(existing_plan.get("active", True))
            if normalized_active:
                _ensure_no_discount_overlap(
                    state,
                    product_id=str(existing_plan["product_id"]),
                    starts_on=normalized_starts_on,
                    ends_on=normalized_ends_on,
                    ignore_discount_plan_id=normalized_discount_plan_id,
                )

            updated_plan = {
                **existing_plan,
                "discount_pct": normalized_discount_pct,
                "plan_name": (plan_name or existing_plan.get("plan_name") or "Discount").strip(),
                "starts_on": normalized_starts_on,
                "ends_on": normalized_ends_on,
                "active": normalized_active,
                "deactivated_at": _utc_now() if active is False else existing_plan.get("deactivated_at"),
                "updated_at": _utc_now(),
            }
            connection.execute(
                f"""
                UPDATE {self.database.qualified('inventory_discount_plans')}
                SET plan_name = %s,
                    discount_pct = %s,
                    starts_on = %s,
                    ends_on = %s,
                    active = %s,
                    updated_at = %s,
                    deactivated_at = %s
                WHERE discount_plan_id = %s
                """,
                (
                    updated_plan["plan_name"],
                    updated_plan["discount_pct"],
                    updated_plan["starts_on"],
                    updated_plan["ends_on"],
                    updated_plan["active"],
                    updated_plan["updated_at"],
                    updated_plan["deactivated_at"],
                    normalized_discount_plan_id,
                ),
            )
            state = self._load_state(connection)
            persisted_plan = next(
                plan for plan in state["discount_plans"] if plan["discount_plan_id"] == normalized_discount_plan_id
            )
            return {
                "action": "update_discount_plan",
                "status": "executed",
                "result": "updated",
                "discount_plan": persisted_plan,
            }

    def deactivate_discount_plan(
        self,
        *,
        discount_plan_id: str | None = None,
        product_id: str | None = None,
    ) -> dict[str, Any]:
        return self.update_discount_plan(
            discount_plan_id=discount_plan_id,
            product_id=product_id,
            active=False,
        )

    def list_discount_plans(
        self,
        *,
        product_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            state = self._load_state(connection)
        plans = state["discount_plans"]
        if product_id is not None:
            normalized_product_id = _normalize_product_id(product_id)
            plans = [plan for plan in plans if str(plan.get("product_id", "")).upper() == normalized_product_id]
        if not include_inactive:
            plans = [plan for plan in plans if bool(plan.get("active", True))]
        plans.sort(key=lambda plan: str(plan.get("discount_plan_id", "")))
        return plans

    def get_stock_levels(self, date_str: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            state = self._load_state(connection)
            status_overrides = self._status_overrides_for_date(connection, date_str)

        results = []
        for product in [product for product in state["products"] if not product.get("is_deleted")]:
            quantity = _resolve_quantity(product, date_str, status_overrides)
            results.append(_build_stock_snapshot(product, quantity, state=state, date_str=date_str))
        return results

    def get_stockout_items(self, date_str: str) -> list[dict[str, Any]]:
        return [item for item in self.get_stock_levels(date_str) if item["status"] == "stockout"]

    def get_low_stock_alerts(self, date_str: str) -> list[dict[str, Any]]:
        return [item for item in self.get_stock_levels(date_str) if item["status"] in ("stockout", "low")]

    def get_conversion_impact(self, date_str: str) -> dict[str, Any]:
        stockouts = self.get_stockout_items(date_str)
        stockout_ids = {item["product_id"] for item in stockouts}
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

    # Phase 2: Date range methods
    def get_stock_levels_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            for item in self.get_stock_levels(date_str):
                result.append({**item, "date": date_str, "period": date_str})
        return result

    def get_stockout_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            stockouts = self.get_stockout_items(date_str)
            result.append(
                {
                    "date": date_str,
                    "period": date_str,
                    "stockout_count": len(stockouts),
                    "items": stockouts,
                }
            )
        return result
