"""Query routes — POST /query, POST /query/stream, GET /query/{run_id}/status."""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.inventory_actions import is_inventory_action_request
from core.orchestrator import get_runtime_graph
from core.run_state import (
    append_run_event,
    get_run_status,
    list_user_query_history,
    list_run_events,
    record_submitted_query,
    store_run_status,
)
from core.state import initial_state
from execution.query_runner import get_query_runner

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    user_id: str = "ops_team"
    date_str: str = "2026-05-31"  # Legacy - kept for backward compatibility
    # Phase 1 additions - optional for backward compatibility
    time_range: dict[str, Any] | None = None  # {"start_date": "2026-05-24", "end_date": "2026-05-31", "granularity": "daily"}
    requested_metrics: list[str] | None = None  # Explicit metric requests
    comparison_baseline: str | None = None  # For period comparisons (e.g., "previous_week")


class QueryResponse(BaseModel):
    run_id: str
    status: str
    message: str


def _normalise_query(query: str) -> str:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return normalized_query


def _is_probably_mutating_query(query: str) -> bool:
    if is_inventory_action_request(query):
        return True
    return re.search(
        r"\b(add|create|remove|delete|update|set|apply|deactivate|disable|increase|decrease|change|restock|discount)\b",
        query,
        flags=re.IGNORECASE,
    ) is not None


def _find_inflight_duplicate_run(user_id: str, query: str, date_str: str) -> dict[str, Any] | None:
    if _is_probably_mutating_query(query):
        return None

    for entry in reversed(list_user_query_history(user_id)):
        if entry.get("query") != query or entry.get("date_str") != date_str:
            continue
        run_id = entry.get("run_id")
        if not isinstance(run_id, str):
            continue
        status = get_run_status(run_id)
        if status is None:
            continue
        if status.get("status") not in {"queued", "running"}:
            continue
        return {"run_id": run_id, "status": status.get("status")}
    return None


@router.post("", response_model=QueryResponse)
async def submit_query(request: QueryRequest) -> QueryResponse:
    """Submit a business query for async processing."""
    normalized_query = _normalise_query(request.query)
    duplicate_run = _find_inflight_duplicate_run(request.user_id, normalized_query, request.date_str)
    if duplicate_run is not None:
        append_run_event(
            duplicate_run["run_id"],
            "duplicate_query_reused",
            user_id=request.user_id,
            query=normalized_query,
            date_str=request.date_str,
        )
        return QueryResponse(
            run_id=duplicate_run["run_id"],
            status=str(duplicate_run["status"]),
            message="Matching in-flight query reused. Poll the existing run for results.",
        )

    run_id = str(uuid.uuid4())
    state = initial_state(
        query=normalized_query,
        run_id=run_id,
        user_id=request.user_id,
        date_str=request.date_str,
    )
    record_submitted_query(run_id, request.user_id, normalized_query, request.date_str)
    store_run_status(run_id, {"status": "running"}, event_type="accepted")
    get_query_runner().submit(run_id, state)

    return QueryResponse(
        run_id=run_id,
        status="running",
        message="Query accepted. Poll /query/{run_id}/status for results.",
    )


@router.get("/{run_id}/status")
async def get_query_status(run_id: str) -> dict:
    """Poll the status and result of a submitted query."""
    status = get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return {"run_id": run_id, **status}


@router.get("/{run_id}/events")
async def get_query_events(run_id: str) -> dict[str, Any]:
    """Return the durable event history for a submitted run."""
    status = get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return {"run_id": run_id, "events": list_run_events(run_id)}


async def _event_stream(state: dict, run_id: str) -> AsyncGenerator[str, None]:
    """Generate SSE events as the graph executes."""
    g = await get_runtime_graph()
    append_run_event(run_id, "stream_started")
    yield f"data: {json.dumps({'event': 'started', 'run_id': run_id})}\n\n"
    try:
        async for chunk in g.astream(
            state, config={"configurable": {"thread_id": run_id}}
        ):
            for node, updates in chunk.items():
                payload = {"event": "node_complete", "node": node}
                if "final_report" in updates and updates["final_report"]:
                    payload["final_report"] = updates["final_report"].model_dump(mode="json")
                append_run_event(run_id, "stream_node_complete", node=node)
                yield f"data: {json.dumps(payload, default=str)}\n\n"

        append_run_event(run_id, "stream_completed")
        yield f"data: {json.dumps({'event': 'completed', 'run_id': run_id})}\n\n"
    except Exception as exc:
        append_run_event(run_id, "stream_error", detail=str(exc))
        yield f"data: {json.dumps({'event': 'error', 'detail': str(exc)})}\n\n"


@router.post("/stream")
async def stream_query(request: QueryRequest) -> StreamingResponse:
    """Stream query execution events via Server-Sent Events."""
    run_id = str(uuid.uuid4())
    normalized_query = _normalise_query(request.query)
    state = initial_state(
        query=normalized_query,
        run_id=run_id,
        user_id=request.user_id,
        date_str=request.date_str,
    )
    record_submitted_query(run_id, request.user_id, normalized_query, request.date_str)
    return StreamingResponse(
        _event_stream(state, run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Run-ID": run_id},
    )
