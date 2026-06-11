"""Tests for direct inventory add requests and persistence."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agents.action_executor import ActionExecutorAgent
from application.repositories import reset_repository_registry
from core.inventory_actions import parse_inventory_action_request, parse_inventory_add_request
from core.orchestrator import final_report_node
from core.settings import reset_settings_cache
from core.state import initial_state
from data.mock.inventory import (
    add_inventory_item,
    create_discount_plan,
    deactivate_discount_plan,
    decrease_inventory_quantity,
    get_stock_levels,
    list_discount_plans,
    remove_inventory_item,
    update_inventory_price,
)
from infrastructure.runtime_store import reset_runtime_store_cache
from models.schemas import (
    ActionRecord,
    ActionStatus,
    ApprovalResponse,
    ApprovalStatus,
    IntentType,
    ReportKind,
    RoutingDecision,
)
from tools.registry import ToolACL, ToolRegistry


class DummyLLMClient:
    async def complete(self, *args, **kwargs):  # pragma: no cover - direct path should bypass the LLM
        raise AssertionError("LLM completion should not be used for direct inventory action requests")


@pytest.fixture(autouse=True)
def isolated_runtime_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RUNTIME_STORE_DIR", str(tmp_path / "runtime-store"))
    reset_repository_registry()
    reset_settings_cache()
    reset_runtime_store_cache()
    ToolRegistry.reset()
    registry = ToolRegistry.get_instance()
    registry.set_acl(
        ToolACL(
            {
                "roles": {
                    "action_executor": {
                        "tools": [
                            "trigger_emergency_restock",
                            "apply_discount_code",
                            "resume_paused_campaign",
                            "add_inventory_item",
                            "increase_inventory_quantity",
                            "decrease_inventory_quantity",
                            "remove_inventory_item",
                            "update_inventory_price",
                            "create_discount_plan",
                            "update_discount_plan",
                            "deactivate_discount_plan",
                            "escalate_to_support_team",
                            "send_customer_notification",
                        ]
                    }
                },
                "agents": {"action_executor": {"role": "action_executor"}},
            }
        )
    )
    yield
    reset_repository_registry()
    ToolRegistry.reset()
    reset_runtime_store_cache()
    reset_settings_cache()


def test_parse_inventory_add_request_extracts_item_details() -> None:
    request = parse_inventory_add_request(
        "Add shirts to inventory with quantity 40 and reorder point 10"
    )

    assert request == {
        "product_name": "Shirts",
        "product_id": None,
        "quantity_available": 40,
        "reorder_point": 10,
        "lead_days": 5,
    }


def test_parse_inventory_add_request_strips_command_prefixes() -> None:
    request = parse_inventory_add_request(
        "Add a new product named Clothes with 78 units into the inventory"
    )

    assert request == {
        "product_name": "Clothes",
        "product_id": None,
        "quantity_available": 78,
        "reorder_point": 25,
        "lead_days": 5,
    }


def test_parse_inventory_action_request_extracts_quantity_decrease() -> None:
    request = parse_inventory_action_request("Remove 25 units from SKU-001")

    assert request is not None
    assert request["tool_name"] == "decrease_inventory_quantity"
    assert request["tool_args"] == {"product_id": "SKU-001", "quantity_delta": 25}


def test_parse_inventory_action_request_extracts_price_update() -> None:
    request = parse_inventory_action_request("Set SKU-003 price to 89.99")

    assert request is not None
    assert request["tool_name"] == "update_inventory_price"
    assert request["tool_args"]["product_id"] == "SKU-003"
    assert request["tool_args"]["unit_price"] == 89.99


def test_parse_inventory_action_request_extracts_discount_creation() -> None:
    request = parse_inventory_action_request("Apply 20% discount to SKU-004 until 2026-06-30")

    assert request is not None
    assert request["tool_name"] == "create_discount_plan"
    assert request["tool_args"]["product_id"] == "SKU-004"
    assert request["tool_args"]["discount_pct"] == 20.0
    assert request["tool_args"]["ends_on"] == "2026-06-30"


def test_parse_inventory_action_request_extracts_discount_update_by_product() -> None:
    request = parse_inventory_action_request("Update discount for SKU-004 to 10% until 2026-06-30")

    assert request is not None
    assert request["tool_name"] == "update_discount_plan"
    assert request["tool_args"]["discount_plan_id"] is None
    assert request["tool_args"]["product_id"] == "SKU-004"
    assert request["tool_args"]["discount_pct"] == 10.0
    assert request["tool_args"]["ends_on"] == "2026-06-30"


def test_parse_inventory_action_request_extracts_discount_deactivation_by_product() -> None:
    request = parse_inventory_action_request("Deactivate discount for SKU-004")

    assert request is not None
    assert request["tool_name"] == "deactivate_discount_plan"
    assert request["tool_args"] == {"discount_plan_id": None, "product_id": "SKU-004"}


def test_add_inventory_item_persists_for_future_stock_levels() -> None:
    result = add_inventory_item(
        product_name="Shirts",
        quantity_available=40,
        reorder_point=10,
    )

    stock_levels = get_stock_levels("2026-06-03")
    shirts = next(item for item in stock_levels if item["product_name"] == "Shirts")

    assert result["result"] == "created"
    assert shirts["quantity_available"] == 40
    assert shirts["reorder_point"] == 10
    assert shirts["status"] == "healthy"


def test_decrease_inventory_quantity_persists_for_existing_products() -> None:
    result = decrease_inventory_quantity(product_id="SKU-001", quantity_delta=15)

    updated_stock_levels = get_stock_levels("2026-06-03")
    headphones_after = next(item for item in updated_stock_levels if item["product_id"] == "SKU-001")

    assert result["result"] == "updated"
    assert result["applied_quantity_delta"] == 15
    assert result["before"]["quantity_available"] - result["after"]["quantity_available"] == 15
    assert headphones_after["quantity_available"] == result["product"]["quantity_available"]


def test_remove_inventory_item_soft_deletes_product_from_stock_levels() -> None:
    result = remove_inventory_item(product_id="SKU-002", reason="discontinued")
    stock_levels = get_stock_levels("2026-06-03")

    assert result["result"] == "removed"
    assert result["product"]["status"] == "removed"
    assert result["product"]["is_deleted"] is True
    assert all(item["product_id"] != "SKU-002" for item in stock_levels)


def test_price_and_discount_plan_updates_are_reflected_in_stock_snapshot() -> None:
    price_result = update_inventory_price(product_id="SKU-003", unit_price=89.99)
    discount_result = create_discount_plan(
        product_id="SKU-003",
        discount_pct=20,
        plan_name="June Recovery",
        starts_on="2026-06-01",
        ends_on="2026-06-30",
    )

    stock_levels = get_stock_levels("2026-06-03")
    hub = next(item for item in stock_levels if item["product_id"] == "SKU-003")
    discount_plans = list_discount_plans(product_id="SKU-003")

    assert price_result["result"] == "updated"
    assert discount_result["result"] == "created"
    assert hub["unit_price"] == 89.99
    assert hub["effective_price"] == 71.99
    assert hub["active_discount"]["plan_name"] == "June Recovery"
    assert discount_plans[0]["discount_plan_id"] == discount_result["discount_plan"]["discount_plan_id"]


def test_deactivate_discount_plan_removes_active_discount_from_snapshot() -> None:
    created = create_discount_plan(
        product_id="SKU-004",
        discount_pct=15,
        plan_name="Weekend Offer",
        starts_on="2026-06-01",
        ends_on="2026-06-30",
    )

    deactivate_discount_plan(discount_plan_id=created["discount_plan"]["discount_plan_id"])
    stock_levels = get_stock_levels("2026-06-03")
    keyboard = next(item for item in stock_levels if item["product_id"] == "SKU-004")

    assert keyboard["active_discount"] is None


def test_update_and_deactivate_discount_plan_can_resolve_active_plan_by_product() -> None:
    created = create_discount_plan(
        product_id="SKU-004",
        discount_pct=15,
        plan_name="Weekend Offer",
        starts_on="2026-06-01",
        ends_on="2026-06-30",
    )

    from tools.action_tools import deactivate_discount_plan as deactivate_discount_tool
    from tools.action_tools import update_discount_plan as update_discount_tool

    updated = update_discount_tool(product_id="SKU-004", discount_pct=10, ends_on="2026-06-25")
    stock_levels_after_update = get_stock_levels("2026-06-03")
    keyboard_after_update = next(item for item in stock_levels_after_update if item["product_id"] == "SKU-004")
    deactivated = deactivate_discount_tool(product_id="SKU-004")
    stock_levels_after_deactivate = get_stock_levels("2026-06-03")
    keyboard_after_deactivate = next(item for item in stock_levels_after_deactivate if item["product_id"] == "SKU-004")

    assert created["discount_plan"]["discount_plan_id"] == updated["discount_plan"]["discount_plan_id"]
    assert updated["discount_plan"]["discount_pct"] == 10.0
    assert updated["discount_plan"]["ends_on"] == "2026-06-25"
    assert keyboard_after_update["active_discount"]["discount_pct"] == 10.0
    assert deactivated["discount_plan"]["discount_plan_id"] == created["discount_plan"]["discount_plan_id"]
    assert keyboard_after_deactivate["active_discount"] is None


def test_apply_discount_code_persists_discount_plan_for_marketing_actions() -> None:
    from data.mock.marketing import get_active_promotions
    from tools.action_tools import apply_discount_code

    today = datetime.now(UTC).date().isoformat()
    result = apply_discount_code(20, ["SKU-005"], expiry_hours=48)
    discount_plans = list_discount_plans(product_id="SKU-005")
    active_promotions = get_active_promotions(today)

    assert result["result"] == "created"
    assert len(discount_plans) == 1
    assert any(promotion.get("campaign_id") == discount_plans[0]["discount_plan_id"] for promotion in active_promotions)


@pytest.mark.asyncio
async def test_action_executor_proposes_add_inventory_item_without_llm() -> None:
    from tools.action_tools import register_action_tools

    register_action_tools()
    agent = ActionExecutorAgent(DummyLLMClient())
    state = initial_state(
        query="Add shirts to inventory with quantity 40 and reorder point 10",
        run_id="run-add-001",
        user_id="store_owner",
    )

    result = await agent._propose_actions(state, state["query"], analysis=None)

    assert result["approval_status"] == ApprovalStatus.PENDING
    assert result["action_proposals"][0].tool_name == "add_inventory_item"
    assert result["action_proposals"][0].tool_args["product_name"] == "Shirts"
    assert result["action_proposals"][0].tool_args["quantity_available"] == 40


@pytest.mark.asyncio
async def test_action_executor_proposes_quantity_decrease_without_llm() -> None:
    from tools.action_tools import register_action_tools

    register_action_tools()
    agent = ActionExecutorAgent(DummyLLMClient())
    state = initial_state(
        query="Remove 25 units from SKU-001",
        run_id="run-decrease-001",
        user_id="store_owner",
    )

    result = await agent._propose_actions(state, state["query"], analysis=None)

    assert result["approval_status"] == ApprovalStatus.PENDING
    assert result["action_proposals"][0].tool_name == "decrease_inventory_quantity"
    assert result["action_proposals"][0].tool_args == {"product_id": "SKU-001", "quantity_delta": 25}


@pytest.mark.asyncio
async def test_final_report_node_prefers_inventory_add_result() -> None:
    state = initial_state(
        query="Add shirts to inventory",
        run_id="run-add-002",
        user_id="store_owner",
    )
    state.update(
        {
            "routing_decision": RoutingDecision(
                intent=IntentType.ACTION,
                active_domains=[],
                reasoning="Direct inventory add request",
                requires_memory_lookup=False,
                requires_action=True,
            ),
            "actions_taken": [
                ActionRecord(
                    action_name="Add Shirts To Inventory",
                    tool_name="add_inventory_item",
                    status=ActionStatus.EXECUTED,
                    result={
                        "action": "add_inventory_item",
                        "result": "created",
                        "product": {
                            "product_id": "SKU-CUSTOM-001",
                            "product_name": "Shirts",
                            "quantity_available": 100,
                            "reorder_point": 25,
                            "status": "healthy",
                            "days_until_stockout": 40.0,
                        },
                    },
                )
            ],
        }
    )

    result = await final_report_node(state)
    report = result["final_report"]

    assert report.analysis is None
    assert report.report_kind == ReportKind.ACTION_CONFIRMATION
    assert report.executive_summary == "Added Shirts to inventory as SKU-CUSTOM-001 with 100 units available."
    assert report.inventory_items[0].product_name == "Shirts"
    assert report.actions_taken[0].action_name == "Add Shirts To Inventory"


@pytest.mark.asyncio
async def test_final_report_node_summarizes_quantity_decrease() -> None:
    state = initial_state(
        query="Remove 15 units from SKU-001",
        run_id="run-decrease-002",
        user_id="store_owner",
    )
    state.update(
        {
            "routing_decision": RoutingDecision(
                intent=IntentType.ACTION,
                active_domains=[],
                reasoning="Direct inventory quantity decrease request",
                requires_memory_lookup=False,
                requires_action=True,
            ),
            "actions_taken": [
                ActionRecord(
                    action_name="Remove 15 Units From SKU-001",
                    tool_name="decrease_inventory_quantity",
                    status=ActionStatus.EXECUTED,
                    result={
                        "action": "decrease_inventory_quantity",
                        "result": "updated",
                        "requested_quantity_delta": 15,
                        "applied_quantity_delta": 15,
                        "product": {
                            "product_id": "SKU-001",
                            "product_name": "Wireless Headphones",
                            "quantity_available": 85,
                            "reorder_point": 50,
                            "status": "healthy",
                            "days_until_stockout": 17.0,
                            "unit_price": 149.99,
                            "currency": "USD",
                            "effective_price": 149.99,
                            "active_discount": None,
                        },
                    },
                )
            ],
        }
    )

    result = await final_report_node(state)
    report = result["final_report"]

    assert report.analysis is None
    assert report.report_kind == ReportKind.ACTION_CONFIRMATION
    assert report.executive_summary == "Removed 15 units from SKU-001. 85 units remain available."
    assert report.inventory_items[0].product_id == "SKU-001"


@pytest.mark.asyncio
async def test_execute_approved_returns_typed_action_records() -> None:
    from tools.action_tools import register_action_tools

    register_action_tools()
    agent = ActionExecutorAgent(DummyLLMClient())
    state = initial_state(
        query="Add shirts to inventory",
        run_id="run-add-003",
        user_id="store_owner",
    )
    state["action_proposals"] = [
        agent._build_direct_inventory_add_result(state, state["query"])["action_proposals"][0]
    ]
    approval_response = ApprovalResponse(
        run_id=state["run_id"],
        approved=True,
        approved_action_names=[state["action_proposals"][0].action_name],
    )

    result = await agent._execute_approved(state, approval_response)

    assert result["approval_status"] == ApprovalStatus.APPROVED
    assert result["actions_taken"][0].status == ActionStatus.EXECUTED
    assert result["actions_taken"][0].tool_name == "add_inventory_item"


@pytest.mark.asyncio
async def test_execute_approved_is_idempotent_for_inventory_mutations() -> None:
    from tools.action_tools import register_action_tools

    register_action_tools()
    agent = ActionExecutorAgent(DummyLLMClient())
    state = initial_state(
        query="Remove 10 units from SKU-001",
        run_id="run-remove-001",
        user_id="store_owner",
    )
    direct_result = agent._build_direct_inventory_action_result(state, state["query"])
    assert direct_result is not None
    state["action_proposals"] = direct_result["action_proposals"]
    approval_response = ApprovalResponse(
        run_id=state["run_id"],
        approved=True,
        approved_action_names=[state["action_proposals"][0].action_name],
    )

    first_result = await agent._execute_approved(state, approval_response)
    second_result = await agent._execute_approved(state, approval_response)
    stock_levels = get_stock_levels("2026-06-03")
    headphones = next(item for item in stock_levels if item["product_id"] == "SKU-001")

    first_record = first_result["actions_taken"][0]
    second_record = second_result["actions_taken"][0]

    assert first_record.status == ActionStatus.EXECUTED
    assert first_record.idempotency_key is not None
    assert second_record.execution_id == first_record.execution_id
    assert second_record.idempotency_key == first_record.idempotency_key
    assert headphones["quantity_available"] == 90
    assert second_record.after_state is not None
    assert second_record.after_state["quantity_available"] == 90
