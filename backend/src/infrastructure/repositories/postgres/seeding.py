"""Seed Postgres-backed repositories from the backend-neutral application seed data."""
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

from data.seeds.app_seed_data import (
    get_inventory_seed,
    get_marketing_seed,
    get_sales_seed,
    get_support_seed,
)
from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase


def _utc_now() -> datetime:
    return datetime.now(UTC)


def seed_repository_data(
    database: PostgresRepositoryDatabase,
    *,
    connection: Any | None = None,
) -> None:
    inventory_seed = get_inventory_seed()
    sales_seed = get_sales_seed()
    marketing_seed = get_marketing_seed()
    support_seed = get_support_seed()

    connection_context = nullcontext(connection) if connection is not None else database.connection()
    with connection_context as active_connection:
        product_table = database.qualified("products")
        status_table = database.qualified("inventory_status_overrides")
        sales_region_table = database.qualified("sales_regions")
        sales_product_table = database.qualified("sales_product_baselines")
        sales_anomaly_table = database.qualified("sales_daily_anomalies")
        campaign_table = database.qualified("marketing_campaigns")
        campaign_override_table = database.qualified("marketing_daily_campaign_overrides")
        complaint_category_table = database.qualified("support_complaint_categories")
        review_topic_table = database.qualified("support_review_topics")
        support_spike_table = database.qualified("support_daily_spikes")

        for product in inventory_seed["products"]:
            active_connection.execute(
                f"""
                INSERT INTO {product_table} (
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
                ON CONFLICT (product_id) DO NOTHING
                """,
                (
                    product["id"],
                    product["name"],
                    int(product["reorder_point"]),
                    int(product["lead_days"]),
                    float(product["unit_price"]),
                    str(product.get("currency", "USD")).upper(),
                    None,
                    "base",
                    None,
                    None,
                    False,
                    None,
                    "",
                ),
            )

        for status_name, dates in (
            ("stockout", inventory_seed["stockout_dates"]),
            ("low", inventory_seed["low_stock_dates"]),
        ):
            for effective_date, product_ids in dates.items():
                for product_id in product_ids:
                    active_connection.execute(
                        f"""
                        INSERT INTO {status_table} (effective_date, product_id, status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (effective_date, product_id)
                        DO UPDATE SET status = EXCLUDED.status
                        """,
                        (effective_date, product_id, status_name),
                    )

        for index, region in enumerate(sales_seed["regions"], start=1):
            active_connection.execute(
                f"""
                INSERT INTO {sales_region_table} (region, sort_order)
                VALUES (%s, %s)
                ON CONFLICT (region) DO UPDATE SET sort_order = EXCLUDED.sort_order
                """,
                (region, index),
            )

        for product in sales_seed["products"]:
            active_connection.execute(
                f"""
                INSERT INTO {sales_product_table} (product_id, product_name, base_revenue, base_orders)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (product_id) DO NOTHING
                """,
                (
                    product["id"],
                    product["name"],
                    float(product["base_revenue"]),
                    int(product["base_orders"]),
                ),
            )

        for effective_date, anomaly in sales_seed["anomaly_dates"].items():
            active_connection.execute(
                f"""
                INSERT INTO {sales_anomaly_table} (
                    effective_date,
                    revenue_drop_pct,
                    order_drop_pct,
                    affected_regions,
                    affected_products,
                    cause
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (effective_date) DO NOTHING
                """,
                (
                    effective_date,
                    float(anomaly["revenue_drop_pct"]),
                    float(anomaly["order_drop_pct"]),
                    list(anomaly["affected_regions"]),
                    list(anomaly["affected_products"]),
                    anomaly["cause"],
                ),
            )

        for campaign in marketing_seed["campaigns"]:
            active_connection.execute(
                f"""
                INSERT INTO {campaign_table} (campaign_id, campaign_name, channel, budget)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (campaign_id) DO NOTHING
                """,
                (
                    campaign["id"],
                    campaign["name"],
                    campaign["channel"],
                    float(campaign["budget"]),
                ),
            )

        overrides: dict[tuple[str, str], dict[str, float | bool | None]] = defaultdict(
            lambda: {"is_paused": False, "roas_factor": None}
        )
        for effective_date, campaign_ids in marketing_seed["paused_dates"].items():
            for campaign_id in campaign_ids:
                overrides[(effective_date, campaign_id)]["is_paused"] = True
        for effective_date, factors in marketing_seed["underperform_dates"].items():
            for campaign_id, roas_factor in factors.items():
                overrides[(effective_date, campaign_id)]["roas_factor"] = float(roas_factor)

        for (effective_date, campaign_id), override in overrides.items():
            active_connection.execute(
                f"""
                INSERT INTO {campaign_override_table} (effective_date, campaign_id, is_paused, roas_factor)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (effective_date, campaign_id) DO UPDATE
                SET is_paused = EXCLUDED.is_paused,
                    roas_factor = EXCLUDED.roas_factor
                """,
                (
                    effective_date,
                    campaign_id,
                    bool(override["is_paused"]),
                    override["roas_factor"],
                ),
            )

        for index, category in enumerate(support_seed["complaint_categories"], start=1):
            active_connection.execute(
                f"""
                INSERT INTO {complaint_category_table} (category, sort_order)
                VALUES (%s, %s)
                ON CONFLICT (category) DO UPDATE SET sort_order = EXCLUDED.sort_order
                """,
                (category, index),
            )

        for index, topic in enumerate(support_seed["review_topics"], start=1):
            active_connection.execute(
                f"""
                INSERT INTO {review_topic_table} (topic, sort_order)
                VALUES (%s, %s)
                ON CONFLICT (topic) DO UPDATE SET sort_order = EXCLUDED.sort_order
                """,
                (topic, index),
            )

        for effective_date, spike in support_seed["spike_dates"].items():
            active_connection.execute(
                f"""
                INSERT INTO {support_spike_table} (
                    effective_date,
                    complaint_multiplier,
                    refund_spike_pct,
                    primary_category,
                    secondary_category
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (effective_date) DO NOTHING
                """,
                (
                    effective_date,
                    float(spike["complaint_multiplier"]),
                    float(spike["refund_spike_pct"]),
                    spike["primary_category"],
                    spike.get("secondary_category"),
                ),
            )

        active_connection.execute("SELECT %s", (_utc_now(),))
