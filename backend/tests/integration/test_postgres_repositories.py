"""Integration tests for the Postgres repository backend."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from core.settings import AppSettings
from infrastructure.repositories.mock import build_mock_repository_registry
from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase
from infrastructure.repositories.postgres.factory import build_postgres_repository_registry


def _postgres_database_url() -> str:
    return (
        os.getenv("POSTGRES_TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://ops:ops@localhost:5432/ops_brain"
    )


@pytest.fixture
def postgres_settings() -> AppSettings:
    database_url = _postgres_database_url()
    try:
        with psycopg.connect(database_url):
            pass
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"Postgres integration test database is unavailable: {exc}")

    schema = f"test_repo_{uuid.uuid4().hex[:10]}"
    settings = AppSettings(
        database_url=database_url,
        repository_backend="postgres",
        repository_schema=schema,
        checkpoint_backend="memory",
    )
    yield settings
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.mark.integration
def test_repository_database_bootstrap_records_migrations(postgres_settings: AppSettings) -> None:
    database = PostgresRepositoryDatabase.from_settings(postgres_settings)
    from infrastructure.repositories.postgres.migrations import (
        apply_repository_migrations,  # noqa: PLC0415
    )
    from infrastructure.repositories.postgres.seeding import seed_repository_data  # noqa: PLC0415

    apply_repository_migrations(database)
    seed_repository_data(database)

    with database.connection() as connection:
        rows = connection.execute(
            f'SELECT version_name FROM {database.qualified("schema_migrations")} ORDER BY version_name'
        ).fetchall()
    assert [row["version_name"] for row in rows]


@pytest.mark.integration
def test_postgres_repositories_match_seeded_mock_outputs(postgres_settings: AppSettings) -> None:
    mock_registry = build_mock_repository_registry()
    postgres_registry = build_postgres_repository_registry(postgres_settings)

    assert postgres_registry.inventory.get_stock_levels("2026-05-31") == mock_registry.inventory.get_stock_levels("2026-05-31")
    assert postgres_registry.sales.get_revenue_metrics("2026-05-31") == mock_registry.sales.get_revenue_metrics("2026-05-31")
    assert postgres_registry.sales.get_order_volume("2026-05-31") == mock_registry.sales.get_order_volume("2026-05-31")
    assert postgres_registry.sales.get_regional_sales("2026-05-31") == mock_registry.sales.get_regional_sales("2026-05-31")
    assert postgres_registry.sales.get_product_performance("2026-05-31") == mock_registry.sales.get_product_performance("2026-05-31")
    assert postgres_registry.sales.detect_sales_anomaly("2026-05-31") == mock_registry.sales.detect_sales_anomaly("2026-05-31")
    assert postgres_registry.marketing.get_campaign_performance("2026-05-31") == mock_registry.marketing.get_campaign_performance("2026-05-31")
    assert postgres_registry.marketing.get_channel_metrics("2026-05-31") == mock_registry.marketing.get_channel_metrics("2026-05-31")
    assert postgres_registry.marketing.list_paused_campaigns("2026-05-31") == mock_registry.marketing.list_paused_campaigns("2026-05-31")
    assert postgres_registry.support.get_complaint_trends("2026-05-31") == mock_registry.support.get_complaint_trends("2026-05-31")
    assert postgres_registry.support.get_refund_metrics("2026-05-31") == mock_registry.support.get_refund_metrics("2026-05-31")
    assert postgres_registry.support.get_review_sentiment("2026-05-31") == mock_registry.support.get_review_sentiment("2026-05-31")


@pytest.mark.integration
def test_postgres_inventory_mutations_persist(postgres_settings: AppSettings) -> None:
    registry = build_postgres_repository_registry(postgres_settings)

    created = registry.inventory.add_inventory_item(
        product_name="Shirts",
        quantity_available=40,
        reorder_point=10,
    )
    decreased = registry.inventory.decrease_inventory_quantity(
        product_id=created["product"]["product_id"],
        quantity_delta=5,
    )
    price_updated = registry.inventory.update_inventory_price(
        product_id=created["product"]["product_id"],
        unit_price=39.99,
    )
    discount_created = registry.inventory.create_discount_plan(
        product_id=created["product"]["product_id"],
        discount_pct=10,
        plan_name="Launch Promo",
        starts_on="2026-06-01",
        ends_on="2026-06-30",
    )
    snapshot = registry.inventory.get_stock_levels("2026-06-03")
    shirts = next(item for item in snapshot if item["product_name"] == "Shirts")

    assert created["result"] == "created"
    assert decreased["result"] == "updated"
    assert price_updated["product"]["unit_price"] == 39.99
    assert discount_created["discount_plan"]["plan_name"] == "Launch Promo"
    assert shirts["quantity_available"] == 35
    assert shirts["unit_price"] == 39.99
    assert shirts["effective_price"] == 35.99
