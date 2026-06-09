"""Shared deterministic sales projections for mock-domain modules."""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from data.seeds.app_seed_data import get_sales_seed

_SALES_SEED = get_sales_seed()

ANOMALY_DATES: dict[str, dict[str, Any]] = _SALES_SEED["anomaly_dates"]


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xDEAD)


def _base_revenue_for_date(d: date) -> float:
    rng = _seed(d)
    base = 59000.0
    seasonal = 0.72 if d.weekday() >= 5 else 1.0
    noise = rng.uniform(0.93, 1.07)
    return base * seasonal * noise


def get_daily_revenue_projection(date_str: str) -> dict[str, Any]:
    current_date = date.fromisoformat(date_str)
    revenue = _base_revenue_for_date(current_date)
    anomaly = ANOMALY_DATES.get(date_str)
    if anomaly:
        revenue *= 1.0 - anomaly["revenue_drop_pct"]
    return {"date": date_str, "total_revenue": round(revenue, 2)}


def get_order_volume_projection(date_str: str) -> dict[str, Any]:
    current_date = date.fromisoformat(date_str)
    rng = _seed(current_date)
    base_orders = 820
    seasonal = 0.70 if current_date.weekday() >= 5 else 1.0
    orders = int(base_orders * seasonal * rng.uniform(0.93, 1.07))

    anomaly = ANOMALY_DATES.get(date_str)
    if anomaly:
        orders = int(orders * (1.0 - anomaly["order_drop_pct"]))

    previous_orders = int(820 * (0.70 if (current_date - timedelta(days=7)).weekday() >= 5 else 1.0))
    return {
        "date": date_str,
        "total_orders": orders,
        "vs_last_week_pct": round((orders - previous_orders) / previous_orders * 100, 1),
        "avg_order_value": round(get_daily_revenue_projection(date_str)["total_revenue"] / max(orders, 1), 2),
    }
