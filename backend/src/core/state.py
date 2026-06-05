"""LangGraph state definition with safe parallel-write reducers."""
from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from models.schemas import (
    ActionProposal,
    ActionRecord,
    AnalysisResult,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    FinalReport,
    MemoryContext,
    ReflectionResult,
    RoutingDecision,
)


def _merge_findings(a: dict, b: dict) -> dict:
    """Merge domain findings dicts — safe for parallel specialist fan-out."""
    return {**a, **b}


class OpsState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────────
    query: str
    run_id: str
    user_id: str
    date_str: str  # Legacy - kept for backward compatibility
    # Phase 1 addition - optional for backward compatibility
    query_intent: dict[str, Any] | None  # Structured query interpretation

    # ── Routing ───────────────────────────────────────────────────────────────
    routing_decision: RoutingDecision | None
    active_domains: list[str]
    coordinator_requery_hints: dict[str, Any] | None
    prior_active_domain_sets: list[list[str]]

    # ── Memory ────────────────────────────────────────────────────────────────
    memory_context: MemoryContext | None

    # ── Domain analysis — annotated reducer for parallel writes ───────────────
    domain_findings: Annotated[dict[str, Any], _merge_findings]

    # ── Synthesis + Reflection ────────────────────────────────────────────────
    analysis_result: AnalysisResult | None
    reflection_result: ReflectionResult | None
    reflection_iteration: int

    # ── Actions ───────────────────────────────────────────────────────────────
    action_proposals: list[ActionProposal]
    approval_request: ApprovalRequest | None
    approval_response: ApprovalResponse | None
    approval_status: ApprovalStatus
    actions_taken: list[ActionRecord]

    # ── Output ────────────────────────────────────────────────────────────────
    inventory_items: list[dict[str, Any]]
    final_report: FinalReport | None

    # ── LangGraph messages (for in-graph LLM calls if needed) ─────────────────
    messages: Annotated[list, add_messages]


def initial_state(
    query: str,
    run_id: str,
    user_id: str = "ops_team",
    date_str: str = "2026-05-31",
    query_intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fully-initialised OpsState dict for graph invocation."""
    return {
        "query": query,
        "run_id": run_id,
        "user_id": user_id,
        "date_str": date_str,
        "query_intent": query_intent,  # Phase 1 addition
        "routing_decision": None,
        "active_domains": [],
        "coordinator_requery_hints": None,
        "prior_active_domain_sets": [],
        "memory_context": None,
        "domain_findings": {},
        "analysis_result": None,
        "reflection_result": None,
        "reflection_iteration": 0,
        "action_proposals": [],
        "approval_request": None,
        "approval_response": None,
        "approval_status": ApprovalStatus.NONE,
        "actions_taken": [],
        "inventory_items": [],
        "final_report": None,
        "messages": [],
    }
