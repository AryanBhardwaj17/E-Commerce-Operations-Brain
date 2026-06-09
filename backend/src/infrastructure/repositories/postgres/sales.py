"""Postgres sales repository adapter."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any, cast

from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase


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
    return random.Random(d.toordinal() ^ 0xDEAD)


def _base_revenue_for_date(d: date) -> float:
    rng = _seed(d)
    base = 59000.0
    seasonal = 0.72 if d.weekday() >= 5 else 1.0
    noise = rng.uniform(0.93, 1.07)
    return base * seasonal * noise


def _get_daily_revenue(date_str: str, anomaly: dict[str, Any] | None) -> dict[str, Any]:
    d = date.fromisoformat(date_str)
    revenue = _base_revenue_for_date(d)
    if anomaly:
        revenue *= 1.0 - float(anomaly["revenue_drop_pct"])
    return {"date": date_str, "total_revenue": round(revenue, 2)}


class PostgresSalesRepository:
    def __init__(self, database: PostgresRepositoryDatabase) -> None:
        self.database = database

    def _get_anomaly(self, date_str: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT effective_date, revenue_drop_pct::float8 AS revenue_drop_pct,
                       order_drop_pct::float8 AS order_drop_pct,
                       affected_regions, affected_products, cause
                FROM {self.database.qualified('sales_daily_anomalies')}
                WHERE effective_date = %s
                """,
                (date.fromisoformat(date_str),),
            ).fetchone()
        if row is None:
            return None
        return {
            "effective_date": row["effective_date"].isoformat(),
            "revenue_drop_pct": float(row["revenue_drop_pct"]),
            "order_drop_pct": float(row["order_drop_pct"]),
            "affected_regions": list(row["affected_regions"] or []),
            "affected_products": list(row["affected_products"] or []),
            "cause": str(row["cause"]),
        }

    def _get_products(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT product_id AS id, product_name AS name,
                       base_revenue::float8 AS base_revenue, base_orders
                FROM {self.database.qualified('sales_product_baselines')}
                ORDER BY product_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _get_regions(self) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT region FROM {self.database.qualified('sales_regions')} ORDER BY sort_order, region"
            ).fetchall()
        return [str(row["region"]) for row in rows]

    def get_revenue_metrics(self, date_str: str) -> dict[str, Any]:
        d = date.fromisoformat(date_str)
        anomaly = self._get_anomaly(date_str)
        today_rev = _get_daily_revenue(date_str, anomaly)["total_revenue"]
        yesterday_rev = _get_daily_revenue((d - timedelta(days=1)).isoformat(), self._get_anomaly((d - timedelta(days=1)).isoformat()))["total_revenue"]
        last_week_rev = _get_daily_revenue((d - timedelta(days=7)).isoformat(), self._get_anomaly((d - timedelta(days=7)).isoformat()))["total_revenue"]

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

    def get_order_volume(self, date_str: str) -> dict[str, Any]:
        d = date.fromisoformat(date_str)
        rng = _seed(d)
        base_orders = 820
        seasonal = 0.70 if d.weekday() >= 5 else 1.0
        orders = int(base_orders * seasonal * rng.uniform(0.93, 1.07))

        anomaly = self._get_anomaly(date_str)
        if anomaly:
            orders = int(orders * (1.0 - float(anomaly["order_drop_pct"])))

        prev_orders = int(820 * (0.70 if (d - timedelta(days=7)).weekday() >= 5 else 1.0))
        return {
            "date": date_str,
            "total_orders": orders,
            "vs_last_week_pct": round((orders - prev_orders) / prev_orders * 100, 1),
            "avg_order_value": round(_get_daily_revenue(date_str, anomaly)["total_revenue"] / max(orders, 1), 2),
        }

    def get_regional_sales(self, date_str: str) -> list[dict[str, Any]]:
        date.fromisoformat(date_str)
        anomaly = self._get_anomaly(date_str)
        affected = set(anomaly["affected_regions"]) if anomaly else set()

        results = []
        total = _get_daily_revenue(date_str, anomaly)["total_revenue"]
        weights = [0.25, 0.20, 0.22, 0.18, 0.15]
        for region, weight in zip(self._get_regions(), weights, strict=True):
            revenue = total * weight
            if region in affected:
                revenue *= 0.45
            results.append(
                {
                    "region": region,
                    "revenue": round(revenue, 2),
                    "is_underperforming": region in affected,
                }
            )
        return results

    def get_product_performance(self, date_str: str) -> list[dict[str, Any]]:
        anomaly = self._get_anomaly(date_str)
        affected = set(anomaly["affected_products"]) if anomaly else set()

        results = []
        for product in self._get_products():
            product_id = str(product["id"])
            product_name = str(product["name"])
            revenue = cast(float, product["base_revenue"])
            orders = cast(int, product["base_orders"])
            if product_id in affected:
                revenue *= 0.05
                orders = int(orders * 0.05)
            results.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "revenue": round(revenue, 2),
                    "orders": orders,
                    "revenue_contribution_pct": 0.0,
                    "is_affected": product_id in affected,
                }
            )

        total_revenue = sum(cast(float, result["revenue"]) for result in results) or 1.0
        for result in results:
            revenue = cast(float, result["revenue"])
            result["revenue_contribution_pct"] = round(revenue / total_revenue * 100, 1)
        return results

    def detect_sales_anomaly(self, date_str: str) -> dict[str, Any]:
        metrics = self.get_revenue_metrics(date_str)
        anomaly = self._get_anomaly(date_str)
        return {
            "date": date_str,
            "anomaly_detected": metrics["is_anomaly"],
            "severity": "high" if abs(metrics["vs_last_week_pct"]) > 25 else "medium",
            "revenue_change_pct": metrics["vs_last_week_pct"],
            "suspected_cause": anomaly["cause"] if anomaly else "unknown",
            "affected_regions": anomaly["affected_regions"] if anomaly else [],
            "affected_products": anomaly["affected_products"] if anomaly else [],
        }

    # Phase 2: Date range methods
    def get_revenue_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        return [
            {"date": date_str, "period": date_str, **self.get_revenue_metrics(date_str)}
            for date_str in dates
        ]

    def get_order_volume_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        return [
            {"date": date_str, "period": date_str, **self.get_order_volume(date_str)}
            for date_str in dates
        ]

    def get_regional_sales_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            for region in self.get_regional_sales(date_str):
                result.append({**region, "date": date_str, "period": date_str})
        return result

    def get_product_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            for product in self.get_product_performance(date_str):
                result.append({**product, "date": date_str, "period": date_str})
        return result
