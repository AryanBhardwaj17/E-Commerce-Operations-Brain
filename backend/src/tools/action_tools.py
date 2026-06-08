"""Action tools — registered with ToolRegistry at import time."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from application.repositories import (
    get_inventory_repository,
    get_marketing_repository,
    get_support_repository,
)
from tools.registry import ToolDefinition, ToolRegistry

# ── Action result schema ──────────────────────────────────────────────────────

class ActionResult:
    """
    All action tools return an ActionResult.

    Tools may return proposed or executed actions, depending on the runtime path.
    """

    def __init__(self, action: str, params: dict[str, Any], status: str = "proposed") -> None:
        self.action = action
        self.params = params
        self.status = status  # "proposed" | "executed" | "rejected"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "params": self.params, "status": self.status}


# ── Stub actions ──────────────────────────────────────────────────────────────

def trigger_emergency_restock(product_ids: list[str], quantity: int = 500) -> dict:
    """Propose an emergency restock purchase order for the given SKUs."""
    return ActionResult(
        action="emergency_restock",
        params={"product_ids": product_ids, "quantity": quantity},
    ).to_dict()


def apply_discount_code(
    discount_pct: float,
    product_ids: list[str],
    expiry_hours: int = 48,
) -> dict:
    """Create persisted discount plans for the supplied products."""
    starts_on = datetime.now(UTC).date().isoformat()
    ends_on = (datetime.now(UTC) + timedelta(hours=max(int(expiry_hours), 1))).date().isoformat()
    inventory_repository = get_inventory_repository()

    created_plans = [
        inventory_repository.create_discount_plan(
            product_id=product_id,
            discount_pct=discount_pct,
            plan_name=f"{float(discount_pct):.0f}% Recovery Offer",
            starts_on=starts_on,
            ends_on=ends_on,
        )
        for product_id in product_ids
    ]
    return {
        "action": "apply_discount_code",
        "status": "executed",
        "result": "created",
        "discount_pct": float(discount_pct),
        "product_ids": product_ids,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "discount_plans": created_plans,
    }


def pause_campaign(campaign_id: str, reason: str = "") -> dict:
    """Pause an active marketing campaign."""
    marketing_repository = get_marketing_repository()
    return marketing_repository.pause_campaign(campaign_id=campaign_id, reason=reason)


def resume_campaign(campaign_id: str) -> dict:
    """Resume a paused marketing campaign."""
    marketing_repository = get_marketing_repository()
    return marketing_repository.resume_campaign(campaign_id=campaign_id)


def resume_paused_campaign(campaign_ids: list[str]) -> dict:
    """Propose resuming one or more paused marketing campaigns (legacy wrapper)."""
    return ActionResult(
        action="resume_paused_campaign",
        params={"campaign_ids": campaign_ids},
    ).to_dict()


def create_support_ticket(
    title: str,
    description: str,
    priority: str = "medium",
    category: str = "general",
    assigned_to: str | None = None,
) -> dict:
    """Create a new support ticket."""
    support_repository = get_support_repository()
    return support_repository.create_support_ticket(
        title=title,
        description=description,
        priority=priority,
        category=category,
        assigned_to=assigned_to,
    )


def escalate_to_support_team(
    issue_category: str,
    priority: str = "high",
    notes: str = "",
) -> dict:
    """Propose escalating a support issue to the human team (legacy wrapper)."""
    return ActionResult(
        action="escalate_to_support",
        params={"issue_category": issue_category, "priority": priority, "notes": notes},
    ).to_dict()


def send_customer_notification(
    message: str,
    channel: str = "email",
    affected_product_ids: list[str] | None = None,
) -> dict:
    """Propose sending a proactive customer notification."""
    return ActionResult(
        action="send_customer_notification",
        params={
            "message": message,
            "channel": channel,
            "affected_product_ids": affected_product_ids or [],
        },
    ).to_dict()


def add_inventory_item(
    product_name: str,
    product_id: str | None = None,
    quantity_available: int = 100,
    reorder_point: int = 25,
    lead_days: int = 5,
) -> dict:
    """Add a new product to the inventory dataset."""
    return get_inventory_repository().add_inventory_item(
        product_name=product_name,
        product_id=product_id,
        quantity_available=quantity_available,
        reorder_point=reorder_point,
        lead_days=lead_days,
    )


def increase_inventory_quantity(product_id: str, quantity_delta: int) -> dict:
    """Increase available units for an existing inventory item."""
    return get_inventory_repository().increase_inventory_quantity(
        product_id=product_id,
        quantity_delta=quantity_delta,
    )


def decrease_inventory_quantity(product_id: str, quantity_delta: int) -> dict:
    """Decrease available units for an existing inventory item."""
    return get_inventory_repository().decrease_inventory_quantity(
        product_id=product_id,
        quantity_delta=quantity_delta,
    )


def remove_inventory_item(product_id: str, reason: str = "") -> dict:
    """Soft-delete a product from the inventory catalog."""
    return get_inventory_repository().remove_inventory_item(
        product_id=product_id,
        reason=reason,
    )


def update_inventory_price(product_id: str, unit_price: float, currency: str = "USD") -> dict:
    """Update the base unit price for an inventory item."""
    return get_inventory_repository().update_inventory_price(
        product_id=product_id,
        unit_price=unit_price,
        currency=currency,
    )


def create_discount_plan(
    product_id: str,
    discount_pct: float,
    plan_name: str | None = None,
    starts_on: str | None = None,
    ends_on: str | None = None,
) -> dict:
    """Create a persisted discount plan for a specific product."""
    return get_inventory_repository().create_discount_plan(
        product_id=product_id,
        discount_pct=discount_pct,
        plan_name=plan_name,
        starts_on=starts_on,
        ends_on=ends_on,
    )


def update_discount_plan(
    discount_plan_id: str | None = None,
    product_id: str | None = None,
    discount_pct: float | None = None,
    plan_name: str | None = None,
    starts_on: str | None = None,
    ends_on: str | None = None,
    active: bool | None = None,
) -> dict:
    """Update a persisted discount plan."""
    return get_inventory_repository().update_discount_plan(
        discount_plan_id=discount_plan_id,
        product_id=product_id,
        discount_pct=discount_pct,
        plan_name=plan_name,
        starts_on=starts_on,
        ends_on=ends_on,
        active=active,
    )


def deactivate_discount_plan(
    discount_plan_id: str | None = None,
    product_id: str | None = None,
) -> dict:
    """Deactivate a persisted discount plan."""
    return get_inventory_repository().deactivate_discount_plan(
        discount_plan_id=discount_plan_id,
        product_id=product_id,
    )


# ── Registration ──────────────────────────────────────────────────────────────
def register_action_tools() -> None:
    registry = ToolRegistry.get_instance()
    for fn, name, desc in [
        (trigger_emergency_restock, "trigger_emergency_restock", "Propose emergency restock PO"),
        (apply_discount_code, "apply_discount_code", "Propose a discount code to recover sales"),
        (pause_campaign, "pause_campaign", "Pause an active marketing campaign"),
        (resume_campaign, "resume_campaign", "Resume a paused marketing campaign"),
        (resume_paused_campaign, "resume_paused_campaign", "Propose resuming paused campaigns"),
        (create_support_ticket, "create_support_ticket", "Create a new support ticket"),
        (add_inventory_item, "add_inventory_item", "Add a new item to the inventory dataset"),
        (increase_inventory_quantity, "increase_inventory_quantity", "Increase units for an inventory item"),
        (decrease_inventory_quantity, "decrease_inventory_quantity", "Decrease units for an inventory item"),
        (remove_inventory_item, "remove_inventory_item", "Soft-delete an inventory item"),
        (update_inventory_price, "update_inventory_price", "Update the base price for an inventory item"),
        (create_discount_plan, "create_discount_plan", "Create a persisted discount plan for an item"),
        (update_discount_plan, "update_discount_plan", "Update a persisted discount plan"),
        (deactivate_discount_plan, "deactivate_discount_plan", "Deactivate a discount plan"),
        (escalate_to_support_team, "escalate_to_support_team", "Escalate to support team"),
        (send_customer_notification, "send_customer_notification", "Send customer notification"),
    ]:
        registry.register(ToolDefinition(name=name, description=desc, function=fn))
