"""
LangGraph orchestrator — the full StateGraph wiring all agents together.

Topology (Phase 1 - with query_interpreter):
    START → guardrails → {final_report | query_interpreter → memory_reader → coordinator → specialist_fan_out}
       → synthesis → reflection → {re_query | action_executor | final_report}
             → END

Parallel specialist fan-out uses LangGraph Send API.
HITL pause uses LangGraph interrupt().
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents.factory import create_agent
from agents.inventory_analyst import query_requests_inventory_list
from core.guardrails import build_non_business_report, evaluate_query_guardrails
from core.hitl import PendingApprovalsStore, request_human_approval
from core.llm_client import LLMClient
from core.memory_response import build_memory_recall_report
from core.reflection import build_re_query_update, should_reflect
from core.settings import get_settings
from core.state import OpsState
from models import schemas as schema_models
from models.schemas import ApprovalStatus, FinalReport, ReportKind

logger = structlog.get_logger(__name__)

# ── Agent singleton registry (created once, shared across requests) ───────────
_llm_client: LLMClient | None = None
_agents: dict[str, Any] = {}
_runtime_graph: Any | None = None
_runtime_checkpointer: Any | None = None
_runtime_checkpointer_context: AbstractAsyncContextManager[Any] | AbstractContextManager[Any] | None = None


def _action_field(action: Any, field: str) -> Any:
    if isinstance(action, dict):
        return action.get(field)
    return getattr(action, field, None)


def _extract_direct_action_record(actions_taken: list[Any]) -> Any | None:
    for action in actions_taken:
        if _action_field(action, "status") not in {
            schema_models.ActionStatus.EXECUTED,
            schema_models.ActionStatus.FAILED,
        }:
            continue
        return action
    return None


def _extract_action_product(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    for key in ("product", "after", "before"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return None


def _format_money(amount: Any, currency: Any) -> str:
    if isinstance(amount, (int, float)):
        return f"{currency} {float(amount):.2f}"
    return f"{currency} {amount}"


def _build_action_confirmation_summary(action: Any) -> str:
    tool_name = _action_field(action, "tool_name") or "action"
    action_name = _action_field(action, "action_name") or "the requested action"
    status = _action_field(action, "status")
    result = _action_field(action, "result")

    if status == schema_models.ActionStatus.FAILED:
        error = _action_field(action, "error") or "Execution failed."
        return f"Could not complete {action_name}: {error}"

    product = _extract_action_product(result)
    product_id = product.get("product_id") if isinstance(product, dict) else ""
    product_name = product.get("product_name") if isinstance(product, dict) else "the requested item"

    if not isinstance(result, dict):
        return f"Executed {action_name}."

    if tool_name == "add_inventory_item":
        quantity_available = product.get("quantity_available") if isinstance(product, dict) else None
        action_result = result.get("result")
        if action_result == "already_exists":
            return f"{product_name} is already in inventory as {product_id}."
        if action_result == "restored":
            return f"Restored {product_name} in inventory as {product_id} with {quantity_available} units available."
        return f"Added {product_name} to inventory as {product_id} with {quantity_available} units available."

    if tool_name == "increase_inventory_quantity":
        quantity_delta = result.get("quantity_delta")
        quantity_available = product.get("quantity_available") if isinstance(product, dict) else None
        return f"Added {quantity_delta} units to {product_id}. {quantity_available} units are now available."

    if tool_name == "decrease_inventory_quantity":
        quantity_delta = result.get("applied_quantity_delta") or result.get("requested_quantity_delta")
        quantity_available = product.get("quantity_available") if isinstance(product, dict) else None
        return f"Removed {quantity_delta} units from {product_id}. {quantity_available} units remain available."

    if tool_name == "remove_inventory_item":
        if result.get("result") == "already_removed":
            return f"{product_id} is already removed from the active inventory catalog."
        return f"Removed {product_id} from the active inventory catalog."

    if tool_name == "update_inventory_price":
        currency = product.get("currency") if isinstance(product, dict) else "USD"
        unit_price = product.get("unit_price") if isinstance(product, dict) else None
        return f"Updated {product_id} base price to {_format_money(unit_price, currency)}."

    if tool_name == "create_discount_plan":
        discount_plan = result.get("discount_plan") or {}
        return (
            f"Created discount plan {discount_plan.get('discount_plan_id', '')} for {product_id} "
            f"at {discount_plan.get('discount_pct', 0)}% off."
        )

    if tool_name == "update_discount_plan":
        discount_plan = result.get("discount_plan") or {}
        return (
            f"Updated discount plan {discount_plan.get('discount_plan_id', '')} to "
            f"{discount_plan.get('discount_pct', 0)}% off."
        )

    if tool_name == "deactivate_discount_plan":
        discount_plan = result.get("discount_plan") or {}
        return f"Deactivated discount plan {discount_plan.get('discount_plan_id', '')}."

    return f"Executed {action_name}."


def _build_specialist_sends(state: OpsState) -> list[Send]:
    active_domains = state.get("active_domains", [])
    sends = []
    domain_to_agent = {
        "SALES": "sales_analyst_node",
        "INVENTORY": "inventory_analyst_node",
        "MARKETING": "marketing_analyst_node",
        "SUPPORT": "support_analyst_node",
    }
    for domain in active_domains:
        node_name = domain_to_agent.get(domain.upper())
        if node_name:
            sends.append(Send(node_name, state))
    return sends


def _get_agent(name: str) -> Any:
    global _llm_client, _agents
    if _llm_client is None:
        settings = get_settings()
        _llm_client = LLMClient(
            default_model=settings.default_model,
            fallback_model=settings.fallback_model,
            settings=settings,
        )
    if name not in _agents:
        _agents[name] = create_agent(name, _llm_client)
    return _agents[name]


# ── Node functions ─────────────────────────────────────────────────────────────

async def memory_reader_node(state: OpsState) -> dict:
    agent = _get_agent("memory_agent")
    return await agent.run(state)


async def guardrails_node(state: OpsState) -> dict:
    report = evaluate_query_guardrails(state)
    if report is None:
        return {}
    return {"final_report": report}


async def query_interpreter_node(state: OpsState) -> dict:
    """Parse natural language query into structured intent (Phase 1)."""
    agent = _get_agent("query_interpreter")
    return await agent.run(state)


async def coordinator_node(state: OpsState) -> dict:
    agent = _get_agent("coordinator")
    result = await agent.run(state)

    routing = result.get("routing_decision")
    active_domains = result.get("active_domains", [])
    intent = getattr(routing, "intent", None)
    # MEMORY-intent runs legitimately carry no active domains — they are answered from
    # the knowledge bases by the memory_response node, so don't treat them as out-of-scope.
    if intent == schema_models.IntentType.OUT_OF_SCOPE or (
        not active_domains and intent != schema_models.IntentType.MEMORY
    ):
        result["final_report"] = build_non_business_report(
            run_id=state["run_id"],
            query=state["query"],
            summary=(
                "This request does not map cleanly to the store operations domains this assistant "
                "supports. Ask about sales, inventory, marketing, or support."
            ),
        )

    return result


async def memory_response_node(state: OpsState) -> dict:
    """Answer a memory-recall query directly from retrieved KEDB/KADB context."""
    routing = state.get("routing_decision")
    report = build_memory_recall_report(
        run_id=state["run_id"],
        query=state["query"],
        memory_context=state.get("memory_context"),
        intent=getattr(routing, "intent", None),
    )
    logger.info("Memory recall report compiled", run_id=report.run_id)
    return {"final_report": report}


def route_to_specialists(state: OpsState) -> list[Send]:
    """Fan out to specialist analyst nodes in parallel using Send API."""
    return _build_specialist_sends(state)


async def sales_analyst_node(state: OpsState) -> dict:
    return await _get_agent("sales_analyst").run(state)


async def inventory_analyst_node(state: OpsState) -> dict:
    return await _get_agent("inventory_analyst").run(state)


async def marketing_analyst_node(state: OpsState) -> dict:
    return await _get_agent("marketing_analyst").run(state)


async def support_analyst_node(state: OpsState) -> dict:
    return await _get_agent("support_analyst").run(state)


async def synthesis_node(state: OpsState) -> dict:
    return await _get_agent("synthesis_agent").run(state)


async def reflection_node(state: OpsState) -> dict:
    return await _get_agent("reflection_agent").run(state)


async def re_query_node(state: OpsState) -> dict:
    """Reset state for a fresh specialist pass on missing domains."""
    return build_re_query_update(state)


async def action_executor_node(state: OpsState) -> dict:
    agent = _get_agent("action_executor")

    existing_request = PendingApprovalsStore.get_request(state["run_id"])
    existing_response = state.get("approval_response") or PendingApprovalsStore.get_response(state["run_id"])
    if existing_request is not None and existing_response is not None:
        state_copy = dict(state)
        state_copy.update(
            {
                "action_proposals": existing_request.proposals,
                "approval_request": existing_request,
                "approval_response": existing_response,
                "approval_status": ApprovalStatus.PENDING,
            },
        )
        execution_result = await agent._execute_approved(state_copy, existing_response)
        return {
            "action_proposals": existing_request.proposals,
            "approval_request": existing_request,
            "approval_response": existing_response,
            **execution_result,
        }

    result = await agent.run(state)

    # Trigger HITL interrupt if proposals were generated
    approval_req = result.get("approval_request")
    if approval_req and result.get("approval_status") == ApprovalStatus.PENDING:
        approval_response = request_human_approval(approval_req)
        result["approval_response"] = approval_response

        # Execute approved actions
        state_copy = dict(state)
        state_copy.update(result)
        execution_result = await agent._execute_approved(state_copy, approval_response)
        result.update(execution_result)

    return result


async def final_report_node(state: OpsState) -> dict:
    """Compile all findings into a FinalReport."""
    if state.get("final_report") is not None:
        return {"final_report": state["final_report"]}

    analysis = state.get("analysis_result")
    memory_ctx = state.get("memory_context")
    routing = state.get("routing_decision")
    actions_taken = state.get("actions_taken", [])
    inventory_items = state.get("inventory_items", [])
    wants_inventory_list = query_requests_inventory_list(state["query"])
    direct_action = _extract_direct_action_record(actions_taken)
    reflection = state.get("reflection_result")  # Phase 1
    query_intent = state.get("query_intent")  # Phase 1

    if direct_action is not None and routing and routing.intent == schema_models.IntentType.ACTION and analysis is None:
        result = _action_field(direct_action, "result")
        product = _extract_action_product(result) or {}
        executive_summary = _build_action_confirmation_summary(direct_action)
        report = FinalReport(
            run_id=state["run_id"],
            query=state["query"],
            report_kind=ReportKind.ACTION_CONFIRMATION,
            intent=routing.intent if routing else schema_models.IntentType.ACTION,
            analysis=None,
            inventory_items=[product] if product else [],
            actions_taken=actions_taken,
            actions_pending_approval=[],
            memory_context_used=memory_ctx is not None,
            executive_summary=executive_summary,
            recommendations=[],
            confidence_score=(1.0 if _action_field(direct_action, "status") == schema_models.ActionStatus.EXECUTED else 0.0),
            data_gaps=[],
        )
        logger.info("Final report compiled for direct action", run_id=report.run_id)
        return {"final_report": report}

    if wants_inventory_list and inventory_items:
        executive_summary = (
            f"Inventory list for {state.get('date_str', '')}: {len(inventory_items)} items found."
        )
    else:
        executive_summary = (
            analysis.primary_root_cause if analysis else "Analysis incomplete."
        )

    # Phase 1 - Build completeness summary
    completeness_summary = None
    if reflection and hasattr(reflection, "completeness_check") and reflection.completeness_check:
        cc = reflection.completeness_check
        total_requested = len(cc.requested_metrics)
        total_addressed = len(cc.addressed_metrics)
        if total_requested > 0:
            if total_addressed == total_requested:
                completeness_summary = f"Answered all {total_requested} requested metrics."
            else:
                missing_str = ", ".join(cc.missing_metrics)
                completeness_summary = (
                    f"Answered {total_addressed} of {total_requested} requested metrics. "
                    f"Missing: {missing_str}."
                )

    # Phase 1 - Extract structured gaps and answer quality
    structured_data_gaps = []
    answer_quality = None
    if reflection:
        if hasattr(reflection, "structured_gaps"):
            structured_data_gaps = reflection.structured_gaps
        if hasattr(reflection, "answer_quality"):
            answer_quality = reflection.answer_quality

    # Phase 1 - Get response format from analysis or query_intent
    response_format = None
    if analysis and hasattr(analysis, "response_format"):
        response_format = analysis.response_format
    elif query_intent:
        from models.schemas import ResponseFormat
        fmt_str = query_intent.get("response_format", "diagnosis")
        try:
            response_format = ResponseFormat(fmt_str)
        except ValueError:
            response_format = ResponseFormat.DIAGNOSIS

    report = FinalReport(
        run_id=state["run_id"],
        query=state["query"],
        report_kind=(ReportKind.INVENTORY_LIST if wants_inventory_list else ReportKind.ANALYSIS),
        intent=routing.intent if routing else None,
        analysis=analysis,
        inventory_items=inventory_items if wants_inventory_list else [],
        actions_taken=actions_taken,
        actions_pending_approval=(
            state.get("action_proposals", [])
            if state.get("approval_status") == ApprovalStatus.PENDING
            else []
        ),
        memory_context_used=memory_ctx is not None,
        executive_summary=executive_summary,
        recommendations=(analysis.recommended_actions if analysis else []),
        confidence_score=analysis.confidence_score if analysis else 0.0,
        data_gaps=(
            reflection.gaps if reflection else []  # Legacy field
        ),
        # Phase 1 fields
        response_format=response_format,
        answer_quality=answer_quality,
        structured_data_gaps=structured_data_gaps,
        completeness_summary=completeness_summary,
    )
    logger.info(
        "Final report compiled",
        run_id=report.run_id,
        response_format=response_format,
        answer_quality=answer_quality,
    )
    return {"final_report": report}


# ── Graph routing functions ────────────────────────────────────────────────────

def route_after_reflection(state: OpsState) -> str:
    return should_reflect(state)


def route_after_guardrails(state: OpsState) -> str:
    if state.get("final_report") is not None:
        return "final_report"
    return "query_interpreter"  # Phase 1 - route through interpreter


def route_after_coordinator(state: OpsState) -> list[Send] | str:
    if state.get("final_report") is not None:
        return "final_report"
    routing = state.get("routing_decision")
    if getattr(routing, "intent", None) == schema_models.IntentType.MEMORY:
        return "memory_response"
    sends = route_to_specialists(state)
    if not sends:
        return "final_report"
    return sends


def route_after_re_query(state: OpsState) -> str:
    if state.get("final_report") is not None:
        return "final_report"
    return "coordinator"


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(OpsState)

    # Nodes
    builder.add_node("guardrails", guardrails_node)
    builder.add_node("query_interpreter", query_interpreter_node)  # Phase 1
    builder.add_node("memory_reader", memory_reader_node)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("memory_response", memory_response_node)
    builder.add_node("sales_analyst_node", sales_analyst_node)
    builder.add_node("inventory_analyst_node", inventory_analyst_node)
    builder.add_node("marketing_analyst_node", marketing_analyst_node)
    builder.add_node("support_analyst_node", support_analyst_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("re_query", re_query_node)
    builder.add_node("action_executor", action_executor_node)
    builder.add_node("final_report", final_report_node)

    # Edges
    builder.add_edge(START, "guardrails")
    builder.add_conditional_edges(
        "guardrails",
        route_after_guardrails,
        {
            "query_interpreter": "query_interpreter",  # Phase 1 - route through interpreter
            "final_report": "final_report",
        },
    )
    builder.add_edge("query_interpreter", "memory_reader")  # Phase 1
    builder.add_edge("memory_reader", "coordinator")
    builder.add_conditional_edges("coordinator", route_after_coordinator)
    # Memory-recall answers reuse the terminal report node (it passes through a
    # pre-built final_report unchanged).
    builder.add_edge("memory_response", "final_report")

    # All specialists converge at synthesis
    for specialist in [
        "sales_analyst_node",
        "inventory_analyst_node",
        "marketing_analyst_node",
        "support_analyst_node",
    ]:
        builder.add_edge(specialist, "synthesis")

    builder.add_edge("synthesis", "reflection")

    builder.add_conditional_edges(
        "reflection",
        route_after_reflection,
        {
            "re_query": "re_query",
            "action": "action_executor",
            "final_report": "final_report",
        },
    )

    # Re-query loop: re_query → coordinator → specialists → synthesis → reflection
    builder.add_conditional_edges(
        "re_query",
        route_after_re_query,
        {
            "coordinator": "coordinator",
            "final_report": "final_report",
        },
    )

    builder.add_edge("action_executor", "final_report")
    builder.add_edge("final_report", END)

    return builder


def compile_graph(checkpointer: Any = None) -> Any:
    builder = build_graph()
    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


def _build_checkpoint_serializer() -> Any:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # noqa: PLC0415

    schema_types = (
        schema_models.IntentType,
        schema_models.DomainType,
        schema_models.ApprovalStatus,
        schema_models.RiskLevel,
        schema_models.BusinessQuery,
        schema_models.RoutingDecision,
        schema_models.DataPoint,
        schema_models.DomainFinding,
        schema_models.AnalysisResult,
        schema_models.ReflectionResult,
        schema_models.ActionProposal,
        schema_models.ApprovalRequest,
        schema_models.ApprovalResponse,
        schema_models.MemoryContext,
        schema_models.FinalReport,
    )
    allowed_msgpack_modules = tuple(
        (schema_type.__module__, schema_type.__name__)
        for schema_type in schema_types
    )
    return JsonPlusSerializer(allowed_msgpack_modules=allowed_msgpack_modules)


async def _build_runtime_checkpointer() -> Any:
    global _runtime_checkpointer, _runtime_checkpointer_context
    if _runtime_checkpointer is not None:
        return _runtime_checkpointer

    settings = get_settings()
    backend = settings.checkpoint_backend
    database_url = settings.normalized_database_url()

    if backend == "memory":
        logger.info("Using in-memory LangGraph checkpointer", backend=backend)
        _runtime_checkpointer = MemorySaver()
        return _runtime_checkpointer

    if not database_url:
        if backend == "postgres":
            raise RuntimeError(
                "CHECKPOINT_BACKEND=postgres requires DATABASE_URL to be configured."
            )
        logger.info(
            "DATABASE_URL not configured; using in-memory LangGraph checkpointer",
            backend=backend,
        )
        _runtime_checkpointer = MemorySaver()
        return _runtime_checkpointer

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: PLC0415
    except ImportError as exc:
        if backend == "postgres":
            raise RuntimeError(
                "Postgres checkpoint backend requested but langgraph-checkpoint-postgres "
                "is not installed in this environment."
            ) from exc

        logger.warning(
            "Postgres checkpointer unavailable; falling back to in-memory runtime",
            backend=backend,
            error=str(exc),
        )
        _runtime_checkpointer = MemorySaver()
        return _runtime_checkpointer

    _runtime_checkpointer_context = AsyncPostgresSaver.from_conn_string(
        database_url,
        serde=_build_checkpoint_serializer(),
    )
    _runtime_checkpointer = await _runtime_checkpointer_context.__aenter__()
    await _runtime_checkpointer.setup()
    logger.info("Using Postgres LangGraph checkpointer", backend="postgres")
    return _runtime_checkpointer


async def get_runtime_graph() -> Any:
    global _runtime_graph
    if _runtime_graph is None:
        _runtime_graph = compile_graph(checkpointer=await _build_runtime_checkpointer())
    return _runtime_graph


async def close_runtime_resources() -> None:
    global _runtime_checkpointer, _runtime_checkpointer_context, _runtime_graph

    _runtime_graph = None
    _runtime_checkpointer = None

    if _runtime_checkpointer_context is None:
        return

    try:
        if isinstance(_runtime_checkpointer_context, AbstractAsyncContextManager):
            await _runtime_checkpointer_context.__aexit__(None, None, None)
        else:
            _runtime_checkpointer_context.__exit__(None, None, None)
    finally:
        _runtime_checkpointer_context = None


# ── Module-level graph instance for LangGraph Studio ─────────────────────────
# langgraph.json references this as `./src/core/orchestrator.py:graph`
graph = compile_graph()
