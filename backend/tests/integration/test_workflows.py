"""Integration test for the full orchestration workflow (mocked LLM)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.repositories import reset_repository_registry
from core.settings import reset_settings_cache
from core.state import initial_state
from models.schemas import (
    AnalysisResult,
    DomainFinding,
    DomainType,
    IntentType,
    MemoryContext,
    ReflectionResult,
    RoutingDecision,
)


@pytest.fixture(autouse=True)
def use_mock_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_repository_registry()
    reset_settings_cache()
    yield
    reset_repository_registry()
    reset_settings_cache()


def _make_routing() -> RoutingDecision:
    return RoutingDecision(
        intent=IntentType.DIAGNOSE,
        active_domains=[DomainType.SALES, DomainType.INVENTORY],
        reasoning="Revenue and inventory signals detected",
        requires_memory_lookup=False,
        requires_action=False,
    )


def _make_finding(domain: str) -> DomainFinding:
    return DomainFinding(
        domain=DomainType(domain.lower()),
        summary=f"{domain} analysis complete",
        data_points=[],
        anomalies=[f"{domain} anomaly detected"],
        contributing_factors=["test factor"],
        confidence=0.85,
        tools_called=[],
    )


def _make_analysis() -> AnalysisResult:
    return AnalysisResult(
        findings=[_make_finding("sales")],
        primary_root_cause="Stockout caused revenue drop",
        contributing_factors=["SKU-001 out of stock"],
        confidence_score=0.88,
        is_new_pattern=False,
        recommended_actions=[],
        cross_domain_correlations=["Inventory stockout → sales drop"],
    )


def _make_reflection(ok: bool = True) -> ReflectionResult:
    return ReflectionResult(
        missing_domains=[],
        confidence_ok=ok,
        action_needed=False,
        gaps=[],
        notes="Analysis quality acceptable",
    )


def _make_memory_ctx() -> MemoryContext:
    return MemoryContext(
        kedb_matches=[],
        kadb_matches=[],
    )


@pytest.fixture
def mock_enforcer_complete():
    """Patch OutputEnforcer.enforce to return pre-built schemas."""

    async def _enforce(messages, output_schema, **kwargs):
        if output_schema.__name__ == "RoutingDecision":
            return _make_routing()
        if output_schema.__name__ == "MemoryContext":
            return _make_memory_ctx()
        if output_schema.__name__ == "DomainFinding":
            domain = "SALES"
            for msg in messages:
                if "INVENTORY" in msg.get("content", ""):
                    domain = "INVENTORY"
            return _make_finding(domain)
        if output_schema.__name__ == "AnalysisResult":
            return _make_analysis()
        if output_schema.__name__ == "ReflectionResult":
            return _make_reflection()
        raise ValueError(f"Unexpected schema: {output_schema}")

    return _enforce


@pytest.mark.asyncio
async def test_full_workflow_no_actions(mock_enforcer_complete):
    """
    Full graph run with mocked LLM — verifies graph topology executes without error
    and produces a FinalReport.
    """
    with (
        patch("models.output_enforcer.OutputEnforcer.enforce", side_effect=mock_enforcer_complete),
        patch("memory.kedb.KEDBStore.get_instance") as mock_kedb,
        patch("memory.kadb.KADBStore.get_instance") as mock_kadb,
    ):
        mock_kedb.return_value.search_semantic.return_value = []
        mock_kadb.return_value.search.return_value = []

        from core.orchestrator import compile_graph
        from tools.inventory_tools import register_inventory_tools
        from tools.marketing_tools import register_marketing_tools
        from tools.memory_tools import register_memory_tools
        from tools.registry import ToolRegistry
        from tools.sales_tools import register_sales_tools
        from tools.support_tools import register_support_tools

        ToolRegistry.reset()
        ToolRegistry.get_instance()
        register_sales_tools()
        register_inventory_tools()
        register_marketing_tools()
        register_support_tools()
        register_memory_tools()

        graph = compile_graph()
        state = initial_state(
            query="Why did sales drop on 2026-05-31?",
            run_id="test-run-001",
        )

        result = await graph.ainvoke(state)

        assert result["final_report"] is not None
        assert result["final_report"].query == "Why did sales drop on 2026-05-31?"
        assert result["final_report"].confidence_score > 0.0
        ToolRegistry.reset()


@pytest.mark.asyncio
async def test_workflow_requery_reenters_coordinator() -> None:
    routing_calls = {"count": 0}
    reflection_calls = {"count": 0}

    async def _enforce(messages, output_schema, **kwargs):
        if output_schema.__name__ == "RoutingDecision":
            routing_calls["count"] += 1
            if routing_calls["count"] == 1:
                return RoutingDecision(
                    intent=IntentType.DIAGNOSE,
                    active_domains=[DomainType.SALES],
                    reasoning="Sales signals detected first.",
                    requires_memory_lookup=False,
                    requires_action=False,
                )
            return RoutingDecision(
                intent=IntentType.DIAGNOSE,
                active_domains=[DomainType.SALES, DomainType.INVENTORY],
                reasoning="Reflection hints indicated inventory should be included.",
                requires_memory_lookup=False,
                requires_action=False,
            )
        if output_schema.__name__ == "MemoryContext":
            return _make_memory_ctx()
        if output_schema.__name__ == "DomainFinding":
            domain = "SALES"
            for msg in messages:
                if "INVENTORY" in msg.get("content", ""):
                    domain = "INVENTORY"
            return _make_finding(domain)
        if output_schema.__name__ == "AnalysisResult":
            return _make_analysis()
        if output_schema.__name__ == "ReflectionResult":
            reflection_calls["count"] += 1
            if reflection_calls["count"] == 1:
                return ReflectionResult(
                    missing_domains=[DomainType.INVENTORY],
                    confidence_ok=False,
                    action_needed=False,
                    gaps=["Inventory evidence is missing"],
                    notes="Re-check routing and add inventory coverage.",
                )
            return _make_reflection(ok=True)
        raise ValueError(f"Unexpected schema: {output_schema}")

    with (
        patch("models.output_enforcer.OutputEnforcer.enforce", side_effect=_enforce),
        patch("memory.kedb.KEDBStore.get_instance") as mock_kedb,
        patch("memory.kadb.KADBStore.get_instance") as mock_kadb,
    ):
        mock_kedb.return_value.search_semantic.return_value = []
        mock_kadb.return_value.search.return_value = []

        from core.orchestrator import compile_graph
        from tools.inventory_tools import register_inventory_tools
        from tools.marketing_tools import register_marketing_tools
        from tools.memory_tools import register_memory_tools
        from tools.registry import ToolRegistry
        from tools.sales_tools import register_sales_tools
        from tools.support_tools import register_support_tools

        ToolRegistry.reset()
        ToolRegistry.get_instance()
        register_sales_tools()
        register_inventory_tools()
        register_marketing_tools()
        register_support_tools()
        register_memory_tools()

        graph = compile_graph()
        state = initial_state(
            query="Why did sales drop on 2026-05-31?",
            run_id="test-run-002",
        )

        result = await graph.ainvoke(state)

        assert routing_calls["count"] == 2
        assert result["final_report"] is not None
        assert result["active_domains"] == ["sales", "inventory"]
        assert result["prior_active_domain_sets"] == [["SALES"]]
        ToolRegistry.reset()
