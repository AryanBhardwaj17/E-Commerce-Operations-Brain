"""Versioned schema creation for Postgres-backed repositories."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase


@dataclass(frozen=True, slots=True)
class Migration:
    version_name: str
    statements: tuple[str, ...]

    def render(self, schema: str) -> tuple[str, ...]:
        return tuple(statement.format(schema=schema) for statement in self.statements)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version_name="001_repository_storage",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS {schema}.products (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                reorder_point INTEGER NOT NULL CHECK (reorder_point > 0),
                lead_days INTEGER NOT NULL CHECK (lead_days > 0),
                unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
                currency TEXT NOT NULL,
                quantity_available INTEGER NULL CHECK (quantity_available >= 0),
                source TEXT NOT NULL DEFAULT 'base',
                created_at TIMESTAMPTZ NULL,
                updated_at TIMESTAMPTZ NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMPTZ NULL,
                removal_reason TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.inventory_status_overrides (
                effective_date DATE NOT NULL,
                product_id TEXT NOT NULL REFERENCES {schema}.products(product_id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK (status IN ('stockout', 'low')),
                PRIMARY KEY (effective_date, product_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.inventory_discount_plans (
                discount_plan_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES {schema}.products(product_id) ON DELETE CASCADE,
                plan_name TEXT NOT NULL,
                discount_pct NUMERIC(5, 2) NOT NULL CHECK (discount_pct > 0 AND discount_pct < 100),
                starts_on DATE NULL,
                ends_on DATE NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                deactivated_at TIMESTAMPTZ NULL,
                CHECK (starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.sales_regions (
                region TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL DEFAULT 999
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.sales_product_baselines (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                base_revenue NUMERIC(12, 2) NOT NULL,
                base_orders INTEGER NOT NULL CHECK (base_orders >= 0)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.sales_daily_anomalies (
                effective_date DATE PRIMARY KEY,
                revenue_drop_pct NUMERIC(6, 4) NOT NULL,
                order_drop_pct NUMERIC(6, 4) NOT NULL,
                affected_regions TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                affected_products TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                cause TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.marketing_campaigns (
                campaign_id TEXT PRIMARY KEY,
                campaign_name TEXT NOT NULL,
                channel TEXT NOT NULL,
                budget NUMERIC(12, 2) NOT NULL CHECK (budget >= 0)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.marketing_daily_campaign_overrides (
                effective_date DATE NOT NULL,
                campaign_id TEXT NOT NULL REFERENCES {schema}.marketing_campaigns(campaign_id) ON DELETE CASCADE,
                is_paused BOOLEAN NOT NULL DEFAULT FALSE,
                roas_factor NUMERIC(8, 4) NULL,
                PRIMARY KEY (effective_date, campaign_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.support_complaint_categories (
                category TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL DEFAULT 999
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.support_review_topics (
                topic TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL DEFAULT 999
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS {schema}.support_daily_spikes (
                effective_date DATE PRIMARY KEY,
                complaint_multiplier NUMERIC(8, 4) NOT NULL,
                refund_spike_pct NUMERIC(8, 4) NOT NULL,
                primary_category TEXT NOT NULL REFERENCES {schema}.support_complaint_categories(category),
                secondary_category TEXT NULL REFERENCES {schema}.support_complaint_categories(category)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_inventory_status_overrides_product ON {schema}.inventory_status_overrides (product_id, effective_date)",
            "CREATE INDEX IF NOT EXISTS idx_inventory_discount_plans_product ON {schema}.inventory_discount_plans (product_id, active)",
            "CREATE INDEX IF NOT EXISTS idx_marketing_daily_overrides_campaign ON {schema}.marketing_daily_campaign_overrides (campaign_id, effective_date)",
        ),
    ),
    Migration(
        version_name="002_sales_region_order",
        statements=(
            "ALTER TABLE {schema}.sales_regions ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 999",
            """
            UPDATE {schema}.sales_regions
            SET sort_order = CASE region
                WHEN 'North' THEN 1
                WHEN 'South' THEN 2
                WHEN 'East' THEN 3
                WHEN 'West' THEN 4
                WHEN 'Central' THEN 5
                ELSE sort_order
            END
            """,
        ),
    ),
    Migration(
        version_name="003_support_reference_order",
        statements=(
            "ALTER TABLE {schema}.support_complaint_categories ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 999",
            "ALTER TABLE {schema}.support_review_topics ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 999",
            """
            UPDATE {schema}.support_complaint_categories
            SET sort_order = CASE category
                WHEN 'out_of_stock' THEN 1
                WHEN 'shipping_delay' THEN 2
                WHEN 'product_defect' THEN 3
                WHEN 'payment_failed' THEN 4
                WHEN 'order_cancelled' THEN 5
                WHEN 'wrong_item' THEN 6
                WHEN 'return_issue' THEN 7
                ELSE sort_order
            END
            """,
            """
            UPDATE {schema}.support_review_topics
            SET sort_order = CASE topic
                WHEN 'product quality' THEN 1
                WHEN 'shipping speed' THEN 2
                WHEN 'customer service' THEN 3
                WHEN 'pricing' THEN 4
                WHEN 'packaging' THEN 5
                ELSE sort_order
            END
            """,
        ),
    ),
    Migration(
        version_name="004_support_tickets",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS {schema}.support_tickets (
                ticket_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
                category TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
                assigned_to TEXT NOT NULL DEFAULT 'unassigned',
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                created_by TEXT NOT NULL,
                resolved_at TIMESTAMPTZ NULL,
                resolution_notes TEXT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON {schema}.support_tickets (status, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_priority ON {schema}.support_tickets (priority, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_assigned_to ON {schema}.support_tickets (assigned_to, status)",
        ),
    ),
    Migration(
        version_name="005_marketing_campaign_overrides_notes",
        statements=(
            "ALTER TABLE {schema}.marketing_daily_campaign_overrides ADD COLUMN IF NOT EXISTS notes TEXT NULL",
        ),
    ),
)


def apply_repository_migrations(
    database: PostgresRepositoryDatabase,
    *,
    connection: Any | None = None,
) -> None:
    connection_context = nullcontext(connection) if connection is not None else database.connection()
    with connection_context as active_connection:
        active_connection.execute(f"CREATE SCHEMA IF NOT EXISTS {database.schema}")
        active_connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {database.qualified('schema_migrations')} (
                version_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied_versions = {
            str(row["version_name"])
            for row in active_connection.execute(
                f"SELECT version_name FROM {database.qualified('schema_migrations')}"
            ).fetchall()
        }

        for migration in MIGRATIONS:
            if migration.version_name in applied_versions:
                continue
            for statement in migration.render(database.schema):
                active_connection.execute(statement)
            active_connection.execute(
                f"INSERT INTO {database.qualified('schema_migrations')} (version_name) VALUES (%s)",
                (migration.version_name,),
            )
