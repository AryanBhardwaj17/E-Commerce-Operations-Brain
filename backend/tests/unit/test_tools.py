"""Unit tests for domain tool functions (no LLM, no ChromaDB needed)."""
from __future__ import annotations

import pytest

from application.repositories import reset_repository_registry
from core.settings import reset_settings_cache


@pytest.fixture(autouse=True)
def use_mock_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_repository_registry()
    reset_settings_cache()
    yield
    reset_repository_registry()
    reset_settings_cache()


# ── Sales tools ───────────────────────────────────────────────────────────────

def test_get_revenue_metrics_normal_date():
    from tools.sales_tools import get_revenue_metrics
    result = get_revenue_metrics("2026-06-01")
    assert "revenue" in result
    assert result["revenue"] > 0
    assert "vs_yesterday_pct" in result


def test_get_revenue_metrics_anomaly_date():
    from tools.sales_tools import get_revenue_metrics
    result = get_revenue_metrics("2026-05-31")
    assert result["is_anomaly"] is True
    assert result["vs_last_week_pct"] < -10


def test_detect_sales_anomaly_on_incident_date():
    from tools.sales_tools import detect_sales_anomaly
    result = detect_sales_anomaly("2026-05-31")
    assert result["anomaly_detected"] is True
    assert "SKU-001" in result["affected_products"]


def test_get_product_performance_stockout_products_near_zero():
    from tools.sales_tools import get_product_performance
    products = get_product_performance("2026-05-31")
    affected = {p["product_id"]: p for p in products if p["is_affected"]}
    assert "SKU-001" in affected
    assert affected["SKU-001"]["revenue"] < 1000  # near-zero due to stockout


# ── Inventory tools ───────────────────────────────────────────────────────────

def test_get_stockout_items_on_incident_date():
    from tools.inventory_tools import get_stockout_items
    stockouts = get_stockout_items("2026-05-31")
    stockout_ids = {s["product_id"] for s in stockouts}
    assert "SKU-001" in stockout_ids
    assert "SKU-003" in stockout_ids


def test_get_conversion_impact_non_zero():
    from tools.inventory_tools import get_conversion_impact
    impact = get_conversion_impact("2026-05-31")
    assert impact["stockout_product_count"] >= 3
    assert impact["estimated_lost_revenue"] > 0


# ── Marketing tools ───────────────────────────────────────────────────────────

def test_list_paused_campaigns_on_incident_date():
    from tools.marketing_tools import list_paused_campaigns
    paused = list_paused_campaigns("2026-05-31")
    assert len(paused) >= 2
    paused_ids = {p["campaign_id"] for p in paused}
    assert "CMP-002" in paused_ids


def test_get_active_promotions_excludes_paused():
    from tools.marketing_tools import get_active_promotions, list_paused_campaigns
    active = {p["campaign_id"] for p in get_active_promotions("2026-05-31")}
    paused = {p["campaign_id"] for p in list_paused_campaigns("2026-05-31")}
    assert active.isdisjoint(paused)


# ── Support tools ─────────────────────────────────────────────────────────────

def test_complaint_spike_on_incident_date():
    from tools.support_tools import get_complaint_trends
    result = get_complaint_trends("2026-05-31")
    assert result["is_spike"] is True
    assert result["total_complaints"] > 80


def test_refund_elevated_on_incident_date():
    from tools.support_tools import get_refund_metrics
    result = get_refund_metrics("2026-05-31")
    assert result["is_elevated"] is True
