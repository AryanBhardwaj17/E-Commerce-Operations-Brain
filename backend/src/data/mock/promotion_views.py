"""Read-only promotion views shared across mock-domain modules."""
from __future__ import annotations

from datetime import date
from typing import Any

from data.mock.inventory_discounts import list_discount_plans_snapshot


def list_active_discount_promotions(date_str: str) -> list[dict[str, Any]]:
    effective_date = date.fromisoformat(date_str)
    promotions: list[dict[str, Any]] = []
    for plan in list_discount_plans_snapshot(include_inactive=False):
        starts_on = plan.get("starts_on")
        ends_on = plan.get("ends_on")
        if starts_on and effective_date < date.fromisoformat(starts_on):
            continue
        if ends_on and effective_date > date.fromisoformat(ends_on):
            continue
        promotions.append(
            {
                "campaign_id": plan["discount_plan_id"],
                "campaign_name": plan["plan_name"],
                "channel": "discount_plan",
                "status": "active",
                "spend": 0.0,
                "revenue_attributed": 0.0,
                "roas": 0.0,
                "impressions": 0,
                "clicks": 0,
                "is_underperforming": False,
                "product_id": plan["product_id"],
                "discount_pct": plan["discount_pct"],
            }
        )
    return promotions
