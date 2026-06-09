"""Mock sales data generator with deterministic anomaly injection."""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any, cast

from data.mock.sales_projection import get_daily_revenue_projection, get_order_volume_projection
from data.seeds.app_seed_data import get_sales_seed

_SALES_SEED = get_sales_seed()

# These represent the incidents the agents are built to diagnose.
ANOMALY_DATES: dict[str, dict[str, Any]] = _SALES_SEED["anomaly_dates"]

PRODUCTS = _SALES_SEED["products"]

REGIONS = _SALES_SEED["regions"]


def _seed(d: date) -> random.Random:
    rng = random.Random(d.toordinal() ^ 0xDEAD)
    return rng


def _base_revenue_for_date(d: date) -> float:
    rng = _seed(d)
    base = 59000.0
    # Weekend dip
    seasonal = 0.72 if d.weekday() >= 5 else 1.0
    noise = rng.uniform(0.93, 1.07)
    return base * seasonal * noise


def get_daily_revenue(date_str: str) -> dict[str, Any]:
    return get_daily_revenue_projection(date_str)


def get_revenue_metrics(date_str: str) -> dict[str, Any]:
    d = date.fromisoformat(date_str)
    today_rev = get_daily_revenue(date_str)["total_revenue"]
    yesterday_rev = get_daily_revenue((d - timedelta(days=1)).isoformat())["total_revenue"]
    last_week_rev = get_daily_revenue((d - timedelta(days=7)).isoformat())["total_revenue"]

    vs_yesterday = round((today_rev - yesterday_rev) / yesterday_rev * 100, 1)
    vs_last_week = round((today_rev - last_week_rev) / last_week_rev * 100, 1)

    return {
        "date": date_str,
        "revenue": today_rev,
        "vs_yesterday_pct": vs_yesterday,
        "vs_last_week_pct": vs_last_week,
        "is_anomaly": abs(vs_last_week) > 15.0,
        "anomaly_threshold_pct": 15.0,
    }


def get_order_volume(date_str: str) -> dict[str, Any]:
    return get_order_volume_projection(date_str)


def get_regional_sales(date_str: str) -> list[dict[str, Any]]:
    date.fromisoformat(date_str)
    anomaly = ANOMALY_DATES.get(date_str)
    affected = set(anomaly["affected_regions"]) if anomaly else set()

    results = []
    total = get_daily_revenue(date_str)["total_revenue"]
    weights = [0.25, 0.20, 0.22, 0.18, 0.15]
    for region, weight in zip(REGIONS, weights, strict=True):
        rev = total * weight
        if region in affected:
            rev *= 0.45  # heavy drop in affected regions
        results.append(
            {
                "region": region,
                "revenue": round(rev, 2),
                "is_underperforming": region in affected,
            }
        )
    return results


def get_product_performance(date_str: str) -> list[dict[str, Any]]:
    anomaly = ANOMALY_DATES.get(date_str)
    affected = set(anomaly["affected_products"]) if anomaly else set()

    results = []
    for prod in PRODUCTS:
        product_id = str(prod["id"])
        product_name = str(prod["name"])
        rev = cast(float, prod["base_revenue"])
        orders = cast(int, prod["base_orders"])
        if product_id in affected:
            rev *= 0.05  # near-zero — out of stock
            orders = int(orders * 0.05)
        results.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "revenue": round(rev, 2),
                "orders": orders,
                "revenue_contribution_pct": 0.0,  # filled below
                "is_affected": product_id in affected,
            }
        )

    total_rev = sum(cast(float, result["revenue"]) for result in results) or 1.0
    for r in results:
        revenue = cast(float, r["revenue"])
        r["revenue_contribution_pct"] = round(revenue / total_rev * 100, 1)
    return results


def detect_sales_anomaly(date_str: str) -> dict[str, Any]:
    metrics = get_revenue_metrics(date_str)
    anomaly = ANOMALY_DATES.get(date_str)
    return {
        "date": date_str,
        "anomaly_detected": metrics["is_anomaly"],
        "severity": "high" if abs(metrics["vs_last_week_pct"]) > 25 else "medium",
        "revenue_change_pct": metrics["vs_last_week_pct"],
        "suspected_cause": anomaly["cause"] if anomaly else "unknown",
        "affected_regions": anomaly["affected_regions"] if anomaly else [],
        "affected_products": anomaly["affected_products"] if anomaly else [],
    }
