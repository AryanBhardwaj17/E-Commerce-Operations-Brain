"""Actions routes — POST /actions/{run_id}/approve and /reject."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from core.hitl import PendingApprovalsStore
from core.orchestrator import get_runtime_graph
from core.run_state import append_run_event, mark_run_failed, store_run_result
from models.schemas import ApprovalResponse

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/actions", tags=["actions"])


class ApproveRequest(BaseModel):
    approved_action_names: list[str]


class RejectRequest(BaseModel):
    reason: str = ""


@router.get("/{run_id}/pending")
async def get_pending_actions(run_id: str) -> dict:
    """Return the pending approval request for a run."""
    req = PendingApprovalsStore.get_request(run_id)
    if req is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval request for run '{run_id}'.",
        )
    return {
        "run_id": run_id,
        "context_summary": req.context_summary,
        "proposals": [p.model_dump() for p in req.proposals],
        "requested_at": req.requested_at.isoformat(),
    }


@router.post("/{run_id}/approve")
async def approve_actions(run_id: str, body: ApproveRequest) -> dict:
    """Approve selected actions for a paused run."""
    req = PendingApprovalsStore.get_request(run_id)
    if req is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval request for run '{run_id}'.",
        )

    all_names = {p.action_name for p in req.proposals}
    rejected = list(all_names - set(body.approved_action_names))

    response = ApprovalResponse(
        run_id=run_id,
        approved=len(body.approved_action_names) > 0,
        approved_action_names=body.approved_action_names,
        rejected_action_names=rejected,
    )
    PendingApprovalsStore.submit_response(response)
    append_run_event(run_id, "approval_submitted", approved=True, approved_actions=body.approved_action_names)

    try:
        graph = await get_runtime_graph()
        result = await graph.ainvoke(
            Command(resume=response.model_dump(mode="json")),
            config={"configurable": {"thread_id": run_id}},
        )
        store_run_result(run_id, result)
        PendingApprovalsStore.clear(run_id)
    except Exception as exc:
        logger.error("Action approval resume failed", run_id=run_id, error=str(exc))
        mark_run_failed(run_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to resume run '{run_id}'.")

    logger.info(
        "Actions approved",
        run_id=run_id,
        approved=body.approved_action_names,
        rejected=rejected,
    )
    return {
        "run_id": run_id,
        "status": "approved",
        "approved": body.approved_action_names,
        "rejected": rejected,
    }


@router.post("/{run_id}/reject")
async def reject_actions(run_id: str, body: RejectRequest) -> dict:
    """Reject all actions for a paused run."""
    req = PendingApprovalsStore.get_request(run_id)
    if req is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval request for run '{run_id}'.",
        )

    response = ApprovalResponse(
        run_id=run_id,
        approved=False,
        approved_action_names=[],
        rejected_action_names=[p.action_name for p in req.proposals],
    )
    PendingApprovalsStore.submit_response(response)
    append_run_event(run_id, "approval_submitted", approved=False, reason=body.reason)

    try:
        graph = await get_runtime_graph()
        result = await graph.ainvoke(
            Command(resume=response.model_dump(mode="json")),
            config={"configurable": {"thread_id": run_id}},
        )
        store_run_result(run_id, result)
        PendingApprovalsStore.clear(run_id)
    except Exception as exc:
        logger.error("Action rejection resume failed", run_id=run_id, error=str(exc))
        mark_run_failed(run_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to resume run '{run_id}'.")

    logger.info("All actions rejected", run_id=run_id, reason=body.reason)
    return {"run_id": run_id, "status": "rejected", "reason": body.reason}
