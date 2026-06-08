"""HITL (Human-in-the-Loop) interrupt helpers and approval store."""
from __future__ import annotations

from typing import Any

import structlog
from langgraph.types import interrupt

from infrastructure.runtime_store import get_runtime_store
from models.schemas import ApprovalRequest, ApprovalResponse

logger = structlog.get_logger(__name__)


class PendingApprovalsStore:
    """
    Persistent store for pending HITL approval requests and responses.

    Keyed by run_id. The FastAPI routes write ApprovalResponse here;
    the orchestrator reads from here after resuming from interrupt().
    """

    @classmethod
    def add_request(cls, request: ApprovalRequest) -> None:
        get_runtime_store().save_approval_request(request)
        logger.info("Approval request stored", run_id=request.run_id)

    @classmethod
    def get_request(cls, run_id: str) -> ApprovalRequest | None:
        return get_runtime_store().get_approval_request(run_id)

    @classmethod
    def submit_response(cls, response: ApprovalResponse) -> None:
        get_runtime_store().save_approval_response(response)
        logger.info(
            "Approval response submitted",
            run_id=response.run_id,
            approved=response.approved,
        )

    @classmethod
    def get_response(cls, run_id: str) -> ApprovalResponse | None:
        return get_runtime_store().get_approval_response(run_id)

    @classmethod
    def clear(cls, run_id: str) -> None:
        get_runtime_store().clear_approval(run_id)


def request_human_approval(approval_request: ApprovalRequest) -> ApprovalResponse:
    """
    Pause graph execution via LangGraph interrupt() and wait for human decision.

    The graph will be resumed externally (via POST /actions/{run_id}/approve)
    with the ApprovalResponse injected as the interrupt value.
    """
    logger.info(
        "Requesting human approval",
        run_id=approval_request.run_id,
        proposals=[p.action_name for p in approval_request.proposals],
    )
    PendingApprovalsStore.add_request(approval_request)

    # LangGraph interrupt() suspends execution; the resume value is the response
    response_data: dict[str, Any] = interrupt(
        {
            "type": "approval_required",
            "run_id": approval_request.run_id,
            "context_summary": approval_request.context_summary,
            "proposals": [
                {
                    "action_name": p.action_name,
                    "rationale": p.rationale,
                    "estimated_impact": p.estimated_impact,
                    "risk_level": p.risk_level,
                }
                for p in approval_request.proposals
            ],
        }
    )

    # Deserialise the response injected by the resume call
    if isinstance(response_data, dict):
        return ApprovalResponse(**response_data)
    if isinstance(response_data, ApprovalResponse):
        return response_data

    # Default: reject if unexpected type
    logger.warning("Unexpected approval response type", data=response_data)
    return ApprovalResponse(
        run_id=approval_request.run_id,
        approved=False,
        approved_action_names=[],
        rejected_action_names=[p.action_name for p in approval_request.proposals],
    )
