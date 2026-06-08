"""Helpers for direct inventory mutation requests."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

_INVENTORY_ADD_PATTERNS = (
    r"\b(?:add|create|insert)\s+(?:a\s+new\s+)?(?:item|product|sku)\s+(?:called|named)?\s*(?P<name>.+?)\s+(?:to|into|in)\s+(?:the\s+)?inventory\b",
    r"\b(?:add|create|insert)\s+(?:a\s+new\s+)?(?:item|product|sku)\s+in\s+(?:the\s+)?inventory\s+(?:called|named)\s+(?P<name>.+)\b",
    r"\b(?:add|create|insert)\s+(?P<name>.+?)\s+(?:to|into|in)\s+(?:the\s+)?inventory\b",
)

_GENERIC_NAMES = {
    "inventory",
    "item",
    "new item",
    "product",
    "sku",
    "stock",
}

_WEEKDAY_LOOKUP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def parse_inventory_action_request(query: str) -> dict[str, Any] | None:
    normalized_query = " ".join(query.split())
    lowered_query = normalized_query.lower()

    if not normalized_query:
        return None

    for parser in (
        _parse_add_action_request,
        _parse_quantity_adjustment_request,
        _parse_remove_item_request,
        _parse_price_update_request,
        _parse_discount_creation_request,
        _parse_discount_update_request,
        _parse_discount_deactivation_request,
    ):
        parsed = parser(normalized_query, lowered_query)
        if parsed is not None:
            return parsed
    return None


def is_inventory_action_request(query: str) -> bool:
    return parse_inventory_action_request(query) is not None


def parse_inventory_add_request(query: str) -> dict[str, Any] | None:
    parsed = parse_inventory_action_request(query)
    if parsed is None or parsed["tool_name"] != "add_inventory_item":
        return None
    return parsed["tool_args"]


def _parse_add_action_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    if not any(keyword in lowered_query for keyword in ("add", "create", "insert")):
        return None
    if not any(keyword in lowered_query for keyword in ("inventory", "stock")):
        return None

    normalized_query = " ".join(query.split())

    match = None
    for pattern in _INVENTORY_ADD_PATTERNS:
        match = re.search(pattern, normalized_query, flags=re.IGNORECASE)
        if match:
            break

    if match is None:
        return None

    product_name = _clean_product_name(match.group("name"))
    if not product_name or product_name.lower() in _GENERIC_NAMES:
        return None

    tool_args = {
        "product_name": product_name,
        "product_id": _extract_product_id(normalized_query),
        "quantity_available": _extract_number(
            normalized_query,
            patterns=(
                r"\bquantity\s*(?:of)?\s*(\d+)\b",
                r"\bqty\s*(\d+)\b",
                r"\b(\d+)\s*(?:units|unit|items|item)\b",
            ),
            default=100,
        ),
        "reorder_point": _extract_number(
            normalized_query,
            patterns=(r"\breorder point\s*(?:of)?\s*(\d+)\b",),
            default=25,
        ),
        "lead_days": _extract_number(
            normalized_query,
            patterns=(r"\blead(?: time)?\s*(?:of)?\s*(\d+)\s*days?\b",),
            default=5,
        ),
    }
    return _build_inventory_action(
        action_name=f"Add {product_name} To Inventory",
        tool_name="add_inventory_item",
        tool_args=tool_args,
        rationale=(
            f"The user explicitly asked to add {product_name} to inventory, so the item should be "
            "created directly instead of routed through diagnosis."
        ),
        estimated_impact="Makes the requested item available in future inventory listings and analyses.",
        risk_level="low",
        context_summary=f"Add {product_name} to the inventory catalog.",
        routing_reason="The user explicitly asked to create a new inventory item.",
    )


def is_inventory_add_request(query: str) -> bool:
    return parse_inventory_add_request(query) is not None


def _parse_quantity_adjustment_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    product_id = _extract_product_id(query)
    if product_id is None:
        return None

    decrease_quantity = _extract_number(
        query,
        patterns=(
            r"\b(?:remove|decrease|reduce|deduct)\s+(\d+)\s*(?:units|unit|items|item|pieces|piece)\b",
            r"\b(?:remove|decrease|reduce)\s+(?:inventory|stock)\s+.*?\bby\s+(\d+)\b",
        ),
        default=-1,
    )
    if decrease_quantity > 0 and any(keyword in lowered_query for keyword in ("remove", "decrease", "reduce", "deduct")):
        return _build_inventory_action(
            action_name=f"Remove {decrease_quantity} Units From {product_id}",
            tool_name="decrease_inventory_quantity",
            tool_args={"product_id": product_id, "quantity_delta": decrease_quantity},
            rationale=(
                f"The user explicitly asked to remove units from {product_id}, so inventory quantity "
                "should be decreased directly."
            ),
            estimated_impact="Reduces the available quantity for the requested SKU.",
            risk_level="medium",
            context_summary=f"Decrease available quantity for {product_id} by {decrease_quantity} units.",
            routing_reason="The user explicitly asked to decrease inventory for an existing SKU.",
        )

    increase_quantity = _extract_number(
        query,
        patterns=(
            r"\b(?:add|increase|restock)\s+(\d+)\s*(?:units|unit|items|item|pieces|piece)\b",
            r"\b(?:increase|restock)\s+(?:inventory|stock)\s+.*?\bby\s+(\d+)\b",
        ),
        default=-1,
    )
    if increase_quantity > 0 and any(keyword in lowered_query for keyword in ("increase", "restock", "add")):
        return _build_inventory_action(
            action_name=f"Add {increase_quantity} Units To {product_id}",
            tool_name="increase_inventory_quantity",
            tool_args={"product_id": product_id, "quantity_delta": increase_quantity},
            rationale=(
                f"The user explicitly asked to increase inventory for {product_id}, so quantity should be "
                "updated directly."
            ),
            estimated_impact="Increases the available quantity for the requested SKU.",
            risk_level="low",
            context_summary=f"Increase available quantity for {product_id} by {increase_quantity} units.",
            routing_reason="The user explicitly asked to increase inventory for an existing SKU.",
        )

    return None


def _parse_remove_item_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    product_id = _extract_product_id(query)
    if product_id is None:
        return None
    if any(keyword in lowered_query for keyword in ("remove", "delete", "discontinue")) and not re.search(
        r"\b(?:remove|decrease|reduce|deduct)\s+\d+\s*(?:units|unit|items|item|pieces|piece)\b",
        query,
        flags=re.IGNORECASE,
    ):
        return _build_inventory_action(
            action_name=f"Remove {product_id} From Inventory",
            tool_name="remove_inventory_item",
            tool_args={"product_id": product_id, "reason": "user_requested_removal"},
            rationale=(
                f"The user explicitly asked to remove {product_id} from the inventory catalog, so the item "
                "should be soft-deleted."
            ),
            estimated_impact="Removes the SKU from active inventory listings while preserving audit history.",
            risk_level="medium",
            context_summary=f"Remove {product_id} from the active inventory catalog.",
            routing_reason="The user explicitly asked to remove an inventory item.",
        )
    return None


def _parse_price_update_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    if "price" not in lowered_query:
        return None
    product_id = _extract_product_id(query)
    if product_id is None:
        return None

    price_match = re.search(
        r"\b(?:price\s+(?:to|at)|set\s+.*?price\s+(?:to|at)|update\s+.*?price\s+(?:to|at)|change\s+.*?price\s+(?:to|at))\s*\$?(\d+(?:\.\d{1,2})?)\b",
        query,
        flags=re.IGNORECASE,
    )
    if price_match is None:
        return None

    unit_price = round(float(price_match.group(1)), 2)
    return _build_inventory_action(
        action_name=f"Update {product_id} Price",
        tool_name="update_inventory_price",
        tool_args={"product_id": product_id, "unit_price": unit_price, "currency": "USD"},
        rationale=(
            f"The user explicitly asked to change the price for {product_id}, so the product price should be "
            "updated directly."
        ),
        estimated_impact="Updates the base unit price used in inventory views and downstream discount calculations.",
        risk_level="medium",
        context_summary=f"Set the base price for {product_id} to USD {unit_price:.2f}.",
        routing_reason="The user explicitly asked to update product pricing.",
    )


def _parse_discount_creation_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    if "discount" not in lowered_query:
        return None
    product_id = _extract_product_id(query)
    if product_id is None:
        return None

    discount_match = re.search(
        r"\b(?:apply|create|set)\s+(\d+(?:\.\d+)?)%\s+discount\b",
        query,
        flags=re.IGNORECASE,
    )
    if discount_match is None:
        return None

    ends_on = _extract_date_phrase(query, prefix="until")
    return _build_inventory_action(
        action_name=f"Create Discount Plan For {product_id}",
        tool_name="create_discount_plan",
        tool_args={
            "product_id": product_id,
            "discount_pct": float(discount_match.group(1)),
            "plan_name": None,
            "starts_on": datetime.now(UTC).date().isoformat(),
            "ends_on": ends_on,
        },
        rationale=(
            f"The user explicitly asked to apply a discount to {product_id}, so a persisted discount plan "
            "should be created directly."
        ),
        estimated_impact="Creates an active discount plan that changes the SKU's effective selling price.",
        risk_level="medium",
        context_summary=f"Create a discount plan for {product_id}.",
        routing_reason="The user explicitly asked to create a discount plan for a SKU.",
    )


def _parse_discount_update_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    if "discount" not in lowered_query:
        return None
    plan_id = _extract_discount_plan_id(query)
    product_id = _extract_product_id(query)
    if plan_id is None and product_id is None:
        return None
    discount_match = re.search(
        r"\b(?:to|at)\s+(\d+(?:\.\d+)?)%",
        query,
        flags=re.IGNORECASE,
    )
    if discount_match is None or not any(keyword in lowered_query for keyword in ("update", "change")):
        return None

    action_target = plan_id or product_id or "discount plan"
    return _build_inventory_action(
        action_name=f"Update {action_target}",
        tool_name="update_discount_plan",
        tool_args={
            "discount_plan_id": plan_id,
            "product_id": product_id,
            "discount_pct": float(discount_match.group(1)),
            "plan_name": None,
            "starts_on": None,
            "ends_on": _extract_date_phrase(query, prefix="until"),
            "active": None,
        },
        rationale=(
            f"The user explicitly asked to update the active discount for {action_target}, so the matching "
            "persisted plan should be updated directly."
        ),
        estimated_impact="Changes the discount percentage or schedule for the existing plan.",
        risk_level="medium",
        context_summary=(
            f"Update discount plan {plan_id}."
            if plan_id is not None
            else f"Update the active discount plan for {product_id}."
        ),
        routing_reason="The user explicitly asked to update an active discount plan.",
    )


def _parse_discount_deactivation_request(query: str, lowered_query: str) -> dict[str, Any] | None:
    if "discount" not in lowered_query:
        return None
    plan_id = _extract_discount_plan_id(query)
    product_id = _extract_product_id(query)
    if plan_id is None and product_id is None:
        return None
    if not any(keyword in lowered_query for keyword in ("deactivate", "disable", "end", "stop")):
        return None
    action_target = plan_id or product_id or "discount plan"
    return _build_inventory_action(
        action_name=f"Deactivate {action_target}",
        tool_name="deactivate_discount_plan",
        tool_args={"discount_plan_id": plan_id, "product_id": product_id},
        rationale=(
            f"The user explicitly asked to deactivate the active discount for {action_target}, so the "
            "matching persisted plan should be disabled directly."
        ),
        estimated_impact="Stops the discount plan from affecting future effective prices.",
        risk_level="medium",
        context_summary=(
            f"Deactivate discount plan {plan_id}."
            if plan_id is not None
            else f"Deactivate the active discount plan for {product_id}."
        ),
        routing_reason="The user explicitly asked to deactivate an active discount plan.",
    )


def _build_inventory_action(
    *,
    action_name: str,
    tool_name: str,
    tool_args: dict[str, Any],
    rationale: str,
    estimated_impact: str,
    risk_level: str,
    context_summary: str,
    routing_reason: str,
) -> dict[str, Any]:
    return {
        "action_name": action_name,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "rationale": rationale,
        "estimated_impact": estimated_impact,
        "risk_level": risk_level,
        "context_summary": context_summary,
        "routing_reason": routing_reason,
    }


def _clean_product_name(value: str) -> str:
    cleaned = re.sub(
        r"\b(with|quantity|qty|reorder point|lead time|lead|sku)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(?:a\s+new\s+)?(?:item|product|sku)\s+(?:named|called)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" .,!?:;")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ""
    if cleaned.islower():
        return cleaned.capitalize()
    return cleaned


def _extract_product_id(query: str) -> str | None:
    exact_match = re.search(r"\b(SKU[-_][A-Za-z0-9_-]+)\b", query, flags=re.IGNORECASE)
    if exact_match is not None:
        return exact_match.group(1).upper().replace("_", "-")

    suffix_match = re.search(r"\bsku\s*[:#]?\s*([A-Za-z0-9_-]+)\b", query, flags=re.IGNORECASE)
    if suffix_match is None:
        return None
    suffix = suffix_match.group(1).upper().lstrip("-_")
    if suffix.startswith("SKU-"):
        return suffix.replace("_", "-")
    return f"SKU-{suffix.replace('_', '-')}"


def _extract_discount_plan_id(query: str) -> str | None:
    match = re.search(r"\bDISC-\d+\b", query, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(0).upper()


def _extract_date_phrase(query: str, *, prefix: str) -> str | None:
    match = re.search(
        rf"\b{prefix}\s+([A-Za-z]+|\d{{4}}-\d{{2}}-\d{{2}})\b",
        query,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    token = match.group(1).strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        return token
    today = datetime.now(UTC).date()
    if token == "today":
        return today.isoformat()
    if token == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if token in _WEEKDAY_LOOKUP:
        days_ahead = (_WEEKDAY_LOOKUP[token] - today.weekday()) % 7
        target_date = today + timedelta(days=days_ahead)
        return target_date.isoformat()
    return None


def _extract_number(query: str, *, patterns: tuple[str, ...], default: int) -> int:
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return default
