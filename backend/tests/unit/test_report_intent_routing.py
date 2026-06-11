"""Regression tests for report-intent inventory list handling."""
from __future__ import annotations

from agents.inventory_analyst import query_requests_inventory_list
from core.orchestrator import route_after_coordinator, route_after_re_query, route_to_specialists
from core.reflection import build_re_query_update, should_reflect
from models.schemas import AnalysisResult, DomainType, IntentType, ReflectionResult, RoutingDecision


def test_query_requests_inventory_list_detects_item_listing() -> None:
    assert query_requests_inventory_list("Give me the list of all items in the inventory") is True
    assert query_requests_inventory_list("Show all stock levels for today") is True
    assert query_requests_inventory_list("Why did inventory availability drop yesterday?") is False


def test_should_reflect_skips_actions_for_report_intent() -> None:
    routing = RoutingDecision(
        intent=IntentType.REPORT,
        active_domains=[],
        reasoning="User requested a listing.",
        requires_memory_lookup=False,
        requires_action=False,
    )
    analysis = AnalysisResult(
        findings=[],
        primary_root_cause="Inventory has stockouts.",
        contributing_factors=[],
        confidence_score=0.9,
        recommended_actions=["trigger_emergency_restock"],
    )

    decision = should_reflect(
        {
            "routing_decision": routing,
            "analysis_result": analysis,
            "reflection_result": None,
            "reflection_iteration": 0,
        }
    )

    assert decision == "final_report"


def test_should_reflect_allows_actions_when_report_explicitly_requires_them() -> None:
    routing = RoutingDecision(
        intent=IntentType.REPORT,
        active_domains=[],
        reasoning="User requested a report plus action plan.",
        requires_memory_lookup=False,
        requires_action=True,
    )
    analysis = AnalysisResult(
        findings=[],
        primary_root_cause="Inventory has stockouts.",
        contributing_factors=[],
        confidence_score=0.9,
        recommended_actions=["trigger_emergency_restock"],
    )

    decision = should_reflect(
        {
            "routing_decision": routing,
            "analysis_result": analysis,
            "reflection_result": None,
            "reflection_iteration": 0,
        }
    )

    assert decision == "action"


def test_route_to_specialists_does_not_fallback_to_all_domains() -> None:
    sends = route_to_specialists({"active_domains": ["unknown"]})

    assert sends == []


def test_route_after_coordinator_finishes_when_no_valid_specialists_exist() -> None:
    decision = route_after_coordinator({"active_domains": ["unknown"], "final_report": None})

    assert decision == "final_report"


def test_route_after_requery_finishes_when_no_valid_specialists_exist() -> None:
    decision = route_after_re_query({"active_domains": [], "final_report": None})

    assert decision == "coordinator"


def test_build_requery_update_preserves_reflection_hints_for_coordinator() -> None:
    update = build_re_query_update(
        {
            "active_domains": ["sales"],
            "prior_active_domain_sets": [],
            "reflection_iteration": 0,
            "reflection_result": ReflectionResult(
                missing_domains=[DomainType.INVENTORY],
                confidence_ok=False,
                action_needed=False,
                gaps=["Inventory data is missing"],
                notes="Re-check routing with inventory included.",
            ),
        }
    )

    assert update["active_domains"] == []
    assert update["prior_active_domain_sets"] == [["SALES"]]
    assert update["coordinator_requery_hints"] == {
        "missing_domains": ["inventory"],
        "confidence_ok": False,
        "gaps": ["Inventory data is missing"],
        "notes": "Re-check routing with inventory included.",
        "previous_active_domains": ["SALES"],
    }


def test_should_reflect_stops_requery_on_repeated_domain_set_without_new_domains() -> None:
    routing = RoutingDecision(
        intent=IntentType.DIAGNOSE,
        active_domains=[DomainType.SALES],
        reasoning="Sales anomaly detected",
        requires_memory_lookup=False,
        requires_action=False,
    )

    decision = should_reflect(
        {
            "routing_decision": routing,
            "analysis_result": None,
            "reflection_result": ReflectionResult(
                missing_domains=[],
                confidence_ok=False,
                action_needed=False,
                gaps=["Confidence still weak"],
                notes="No better domain hypothesis available.",
            ),
            "reflection_iteration": 1,
            "active_domains": ["sales"],
            "prior_active_domain_sets": [["SALES"]],
        }
    )

    assert decision == "final_report"
