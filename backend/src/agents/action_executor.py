"""Action executor agent — proposes HITL-gated corrective actions."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agents.base import BaseAgent
from core.inventory_actions import parse_inventory_action_request
from core.settings import resolve_agent_config_path
from infrastructure.runtime_store import get_runtime_store
from models.schemas import (
    ActionProposal,
    ActionRecord,
    ActionStatus,
    ApprovalRequest,
    ApprovalStatus,
)

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("action_executor.yaml")


class ActionExecutorAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    def _proposal_idempotency_key(self, state: OpsState, proposal: ActionProposal) -> str:
        serialized = json.dumps(
            {
                "run_id": state["run_id"],
                "action_name": proposal.action_name,
                "tool_name": proposal.tool_name,
                "tool_args": proposal.tool_args,
            },
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _load_action_execution(self, run_id: str, idempotency_key: str) -> ActionRecord | None:
        payload = get_runtime_store().get_action_execution(run_id, idempotency_key)
        if payload is None:
            return None
        return ActionRecord.model_validate(payload)

    def _save_action_execution(self, run_id: str, idempotency_key: str, record: ActionRecord) -> None:
        get_runtime_store().save_action_execution(
            run_id,
            idempotency_key,
            record.model_dump(mode="json"),
        )

    def _normalize_tool_args(self, tool_name: str, tool_args: Any) -> dict[str, Any]:
        if not isinstance(tool_args, dict):
            return {}

        def string_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        if tool_name == "trigger_emergency_restock":
            product_ids = string_list(tool_args.get("product_ids"))
            quantity = tool_args.get("quantity")

            if not product_ids and isinstance(tool_args.get("products"), list):
                products = [item for item in tool_args["products"] if isinstance(item, dict)]
                product_ids = [
                    str(item.get("product_id") or item.get("sku") or item.get("name")).strip()
                    for item in products
                    if item.get("product_id") or item.get("sku") or item.get("name")
                ]
                quantities = [
                    int(item["quantity"])
                    for item in products
                    if isinstance(item.get("quantity"), (int, float))
                ]
                if quantities:
                    quantity = max(quantities)

            return {
                "product_ids": product_ids,
                "quantity": int(quantity) if isinstance(quantity, (int, float)) else 500,
            }

        if tool_name == "apply_discount_code":
            product_ids = string_list(tool_args.get("product_ids"))
            if not product_ids and isinstance(tool_args.get("products"), list):
                product_ids = [
                    str(item.get("product_id") or item.get("sku") or item.get("name")).strip()
                    for item in tool_args["products"]
                    if isinstance(item, dict)
                    and (item.get("product_id") or item.get("sku") or item.get("name"))
                ]

            discount_pct = tool_args.get("discount_pct")
            if not isinstance(discount_pct, (int, float)):
                discount_pct = tool_args.get("discount_percentage")

            expiry_hours = tool_args.get("expiry_hours")
            return {
                "discount_pct": float(discount_pct) if isinstance(discount_pct, (int, float)) else 10.0,
                "product_ids": product_ids,
                "expiry_hours": int(expiry_hours) if isinstance(expiry_hours, (int, float)) else 48,
            }

        if tool_name == "pause_campaign":
            campaign_id = tool_args.get("campaign_id") or tool_args.get("id") or ""
            reason = tool_args.get("reason") or tool_args.get("notes") or ""
            return {
                "campaign_id": str(campaign_id).strip(),
                "reason": str(reason).strip(),
            }

        if tool_name == "resume_campaign":
            campaign_id = tool_args.get("campaign_id") or tool_args.get("id") or ""
            return {
                "campaign_id": str(campaign_id).strip(),
            }

        if tool_name == "resume_paused_campaign":
            campaign_ids = string_list(tool_args.get("campaign_ids"))
            if not campaign_ids:
                campaign_ids = string_list(tool_args.get("campaigns"))
            return {"campaign_ids": campaign_ids}

        if tool_name == "add_inventory_item":
            product_name = tool_args.get("product_name") or tool_args.get("name") or ""
            product_id = tool_args.get("product_id") or tool_args.get("sku")
            quantity_available = tool_args.get("quantity_available")
            if not isinstance(quantity_available, (int, float)):
                quantity_available = tool_args.get("quantity")
            reorder_point = tool_args.get("reorder_point")
            lead_days = tool_args.get("lead_days")
            return {
                "product_name": str(product_name).strip(),
                "product_id": str(product_id).strip() if isinstance(product_id, str) and product_id.strip() else None,
                "quantity_available": int(quantity_available) if isinstance(quantity_available, (int, float)) else 100,
                "reorder_point": int(reorder_point) if isinstance(reorder_point, (int, float)) else 25,
                "lead_days": int(lead_days) if isinstance(lead_days, (int, float)) else 5,
            }

        if tool_name in {"increase_inventory_quantity", "decrease_inventory_quantity"}:
            product_id = tool_args.get("product_id") or tool_args.get("sku") or ""
            quantity_delta = tool_args.get("quantity_delta")
            if not isinstance(quantity_delta, (int, float)):
                quantity_delta = tool_args.get("quantity")
            return {
                "product_id": str(product_id).strip().upper(),
                "quantity_delta": int(quantity_delta) if isinstance(quantity_delta, (int, float)) else 1,
            }

        if tool_name == "remove_inventory_item":
            product_id = tool_args.get("product_id") or tool_args.get("sku") or ""
            reason = tool_args.get("reason") or tool_args.get("notes") or ""
            return {
                "product_id": str(product_id).strip().upper(),
                "reason": str(reason).strip(),
            }

        if tool_name == "update_inventory_price":
            product_id = tool_args.get("product_id") or tool_args.get("sku") or ""
            unit_price = tool_args.get("unit_price")
            if not isinstance(unit_price, (int, float)):
                unit_price = tool_args.get("price")
            currency = tool_args.get("currency") or "USD"
            return {
                "product_id": str(product_id).strip().upper(),
                "unit_price": float(unit_price) if isinstance(unit_price, (int, float)) else 0.0,
                "currency": str(currency).strip().upper() or "USD",
            }

        if tool_name == "create_discount_plan":
            product_id = tool_args.get("product_id") or tool_args.get("sku") or ""
            discount_pct = tool_args.get("discount_pct")
            if not isinstance(discount_pct, (int, float)):
                discount_pct = tool_args.get("discount_percentage")
            return {
                "product_id": str(product_id).strip().upper(),
                "discount_pct": float(discount_pct) if isinstance(discount_pct, (int, float)) else 10.0,
                "plan_name": tool_args.get("plan_name") or tool_args.get("name"),
                "starts_on": tool_args.get("starts_on"),
                "ends_on": tool_args.get("ends_on"),
            }

        if tool_name == "update_discount_plan":
            discount_plan_id = tool_args.get("discount_plan_id") or tool_args.get("plan_id") or ""
            product_id = tool_args.get("product_id") or tool_args.get("sku")
            discount_pct = tool_args.get("discount_pct")
            if not isinstance(discount_pct, (int, float)):
                discount_pct = tool_args.get("discount_percentage")
            return {
                "discount_plan_id": str(discount_plan_id).strip().upper() or None,
                "product_id": str(product_id).strip().upper() if isinstance(product_id, str) and product_id.strip() else None,
                "discount_pct": float(discount_pct) if isinstance(discount_pct, (int, float)) else None,
                "plan_name": tool_args.get("plan_name") or tool_args.get("name"),
                "starts_on": tool_args.get("starts_on"),
                "ends_on": tool_args.get("ends_on"),
                "active": tool_args.get("active"),
            }

        if tool_name == "deactivate_discount_plan":
            discount_plan_id = tool_args.get("discount_plan_id") or tool_args.get("plan_id") or ""
            product_id = tool_args.get("product_id") or tool_args.get("sku")
            return {
                "discount_plan_id": str(discount_plan_id).strip().upper() or None,
                "product_id": str(product_id).strip().upper() if isinstance(product_id, str) and product_id.strip() else None,
            }

        if tool_name == "create_support_ticket":
            title = tool_args.get("title") or tool_args.get("subject") or ""
            description = (
                tool_args.get("description")
                or tool_args.get("details")
                or tool_args.get("message")
                or tool_args.get("notes")
                or ""
            )
            priority = str(tool_args.get("priority") or "medium").lower()
            category = (
                tool_args.get("category") or tool_args.get("issue_category") or "general"
            )
            assigned_to = tool_args.get("assigned_to") or tool_args.get("assignee")
            return {
                "title": str(title).strip(),
                "description": str(description).strip(),
                "priority": priority,
                "category": str(category).strip(),
                "assigned_to": str(assigned_to).strip() if assigned_to else None,
            }

        if tool_name == "escalate_to_support_team":
            issue_category = (
                tool_args.get("issue_category")
                or tool_args.get("category")
                or tool_args.get("issue")
                or "operations"
            )
            priority = str(tool_args.get("priority") or "high").lower()
            notes = (
                tool_args.get("notes")
                or tool_args.get("reason")
                or tool_args.get("message")
                or tool_args.get("issue")
                or ""
            )
            return {
                "issue_category": str(issue_category),
                "priority": priority,
                "notes": str(notes),
            }

        if tool_name == "send_customer_notification":
            affected_product_ids = string_list(tool_args.get("affected_product_ids"))
            if not affected_product_ids:
                affected_product_ids = string_list(tool_args.get("product_ids"))
            if not affected_product_ids and isinstance(tool_args.get("products"), list):
                affected_product_ids = [
                    str(item.get("product_id") or item.get("sku") or item.get("name")).strip()
                    for item in tool_args["products"]
                    if isinstance(item, dict)
                    and (item.get("product_id") or item.get("sku") or item.get("name"))
                ]

            return {
                "message": str(tool_args.get("message") or ""),
                "channel": str(tool_args.get("channel") or "email"),
                "affected_product_ids": affected_product_ids,
            }

        return tool_args

    def _normalize_proposal_payload(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        for key in ("proposal", "action_proposal", "actionProposal"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                payload = nested
                break

        action_name = payload.get("action_name") or payload.get("action") or payload.get("name")
        tool_name = payload.get("tool_name") or payload.get("tool") or action_name
        if not action_name and isinstance(tool_name, str) and tool_name.strip():
            action_name = tool_name

        if not isinstance(action_name, str) or not action_name.strip():
            return None
        if not isinstance(tool_name, str) or not tool_name.strip():
            return None

        tool_args = payload.get("tool_args") or payload.get("parameters") or payload.get("args") or {}
        rationale = payload.get("rationale") or payload.get("reason") or payload.get("justification") or ""
        estimated_impact = (
            payload.get("estimated_impact")
            or payload.get("impact")
            or payload.get("expected_impact")
            or ""
        )
        risk_level = str(payload.get("risk_level") or payload.get("risk") or "medium").lower()

        return {
            "action_name": action_name.strip(),
            "tool_name": tool_name.strip(),
            "tool_args": self._normalize_tool_args(str(tool_name), tool_args),
            "rationale": rationale,
            "estimated_impact": estimated_impact,
            "risk_level": risk_level,
        }

    def _build_direct_inventory_action_result(self, state: OpsState, query: str) -> dict[str, Any] | None:
        action_request = parse_inventory_action_request(query)
        if action_request is None:
            return None

        action_name = action_request["action_name"]
        proposal = ActionProposal(
            action_name=action_name,
            tool_name=action_request["tool_name"],
            tool_args=action_request["tool_args"],
            rationale=action_request["rationale"],
            estimated_impact=action_request["estimated_impact"],
            risk_level=action_request["risk_level"],
        )
        approval_req = ApprovalRequest(
            run_id=state["run_id"],
            proposals=[proposal],
            context_summary=action_request["context_summary"],
            requested_at=datetime.now(UTC),
        )
        return {
            "action_proposals": [proposal],
            "approval_request": approval_req,
            "approval_status": ApprovalStatus.PENDING,
        }

    def _build_direct_inventory_add_result(self, state: OpsState, query: str) -> dict[str, Any] | None:
        result = self._build_direct_inventory_action_result(state, query)
        if result is None:
            return None
        first_proposal = result["action_proposals"][0]
        if first_proposal.tool_name != "add_inventory_item":
            return None
        return result

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        analysis = state.get("analysis_result")
        approval_response = state.get("approval_response")

        self.logger.info("Action executor running")

        # --- Phase 1: Build action proposals (before HITL) ---
        if state.get("approval_status") == ApprovalStatus.NONE:
            return await self._propose_actions(state, query, analysis)

        # --- Phase 2: Execute approved actions (after HITL) ---
        return await self._execute_approved(state, approval_response)

    async def _propose_actions(
        self, state: OpsState, query: str, analysis: Any
    ) -> dict[str, Any]:
        """Generate action proposals from the analysis recommendations."""
        direct_inventory_action = self._build_direct_inventory_action_result(state, query)
        if direct_inventory_action is not None:
            self.logger.info("Direct inventory action proposed")
            return direct_inventory_action

        if not analysis:
            return {"action_proposals": [], "approval_status": ApprovalStatus.NONE}

        recommendations_json = json.dumps(
            analysis.recommended_actions if hasattr(analysis, "recommended_actions") else [],
            indent=2,
            default=str,
        )

        tool_list = json.dumps(self.get_tool_descriptions(), indent=2)

        messages = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n\n"
                    f"Analysis recommendations:\n{recommendations_json}\n\n"
                    f"Available action tools:\n{tool_list}\n\n"
                    f"For each recommendation, create an ActionProposal JSON object.\n"
                    f"Use the exact tool names and argument names from the available action tools.\n"
                    f"Return a JSON object with a single 'proposals' array of ActionProposal objects."
                ),
            },
        ]

        raw = await self.llm_client.complete(
            messages=messages,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            timeout=self.timeout,
        )

        try:
            parsed = json.loads(raw)
            proposals_data: Any = parsed
            if isinstance(parsed, dict):
                for key in ("proposals", "action_proposals", "actionProposals"):
                    if key in parsed:
                        proposals_data = parsed[key]
                        break
            if isinstance(proposals_data, dict):
                proposals_data = [proposals_data]
            normalized = [
                proposal
                for proposal in (self._normalize_proposal_payload(p) for p in proposals_data)
                if proposal is not None
            ]
            proposals = [ActionProposal.model_validate(p) for p in normalized]

            unique_proposals: list[ActionProposal] = []
            seen_actions: set[str] = set()
            for proposal in proposals:
                if proposal.action_name in seen_actions:
                    continue
                seen_actions.add(proposal.action_name)
                unique_proposals.append(proposal)
            proposals = unique_proposals
        except Exception as exc:
            self.logger.warning("Action proposal parsing failed", error=str(exc))
            proposals = []

        if not proposals:
            self.logger.info("No actionable proposals generated")
            return {
                "action_proposals": [],
                "approval_request": None,
                "approval_status": ApprovalStatus.NONE,
            }

        approval_req = ApprovalRequest(
            run_id=state["run_id"],
            proposals=proposals,
            context_summary=getattr(analysis, "executive_summary", str(analysis))[:500],
            requested_at=datetime.now(UTC),
        )

        self.logger.info("Action proposals generated", count=len(proposals))
        return {
            "action_proposals": proposals,
            "approval_request": approval_req,
            "approval_status": ApprovalStatus.PENDING,
        }

    async def _execute_approved(
        self, state: OpsState, approval_response: Any
    ) -> dict[str, Any]:
        """Execute actions that have been approved by the human operator."""
        if not approval_response or not approval_response.approved:
            self.logger.info("All actions rejected by operator")
            return {"approval_status": ApprovalStatus.REJECTED, "actions_taken": []}

        proposals: list[ActionProposal] = state.get("action_proposals", [])
        approved_names = set(approval_response.approved_action_names)
        actions_taken = []
        run_id = state["run_id"]

        for proposal in proposals:
            if proposal.action_name in approved_names:
                idempotency_key = self._proposal_idempotency_key(state, proposal)
                existing_record = self._load_action_execution(run_id, idempotency_key)
                if existing_record is not None:
                    actions_taken.append(existing_record)
                    self.logger.info(
                        "Action execution reused from idempotent store",
                        action=proposal.action_name,
                        idempotency_key=idempotency_key,
                    )
                    continue

                execution_id = uuid4().hex
                executed_at = datetime.now(UTC)
                try:
                    result = self.call_tool(proposal.tool_name, **proposal.tool_args)
                    record = ActionRecord(
                        action_name=proposal.action_name,
                        tool_name=proposal.tool_name,
                        result=result,
                        status=ActionStatus.EXECUTED,
                        idempotency_key=idempotency_key,
                        execution_id=execution_id,
                        executed_at=executed_at,
                        before_state=result.get("before") if isinstance(result, dict) else None,
                        after_state=(
                            result.get("after") or result.get("product")
                            if isinstance(result, dict)
                            else None
                        ),
                    )
                    self._save_action_execution(run_id, idempotency_key, record)
                    actions_taken.append(record)
                    self.logger.info("Action executed", action=proposal.action_name)
                except Exception as exc:
                    self.logger.error(
                        "Action execution failed",
                        action=proposal.action_name,
                        error=str(exc),
                    )
                    record = ActionRecord(
                        action_name=proposal.action_name,
                        tool_name=proposal.tool_name,
                        error=str(exc),
                        status=ActionStatus.FAILED,
                        idempotency_key=idempotency_key,
                        execution_id=execution_id,
                        executed_at=executed_at,
                    )
                    self._save_action_execution(run_id, idempotency_key, record)
                    actions_taken.append(record)

        return {
            "actions_taken": actions_taken,
            "approval_status": ApprovalStatus.APPROVED,
        }
