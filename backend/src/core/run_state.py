"""Helpers for persisting run status and event history."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from infrastructure.runtime_store import get_runtime_store


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _serialise_approval_status(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def append_run_event(run_id: str, event_type: str, **payload: Any) -> None:
    get_runtime_store().append_run_event(
        run_id,
        {
            "type": event_type,
            "timestamp": _timestamp(),
            **payload,
        },
    )


def record_submitted_query(run_id: str, user_id: str, query: str, date_str: str) -> None:
    get_runtime_store().append_user_query(
        user_id,
        {
            "run_id": run_id,
            "user_id": user_id,
            "query": query,
            "date_str": date_str,
            "timestamp": _timestamp(),
        },
    )


def list_user_query_history(user_id: str) -> list[dict[str, Any]]:
    return get_runtime_store().list_user_queries(user_id)


def store_run_status(run_id: str, status: dict[str, Any], *, event_type: str | None = None) -> None:
    current = get_runtime_store().get_run_status(run_id) or {}
    payload = {
        **current,
        **status,
        "updated_at": _timestamp(),
    }
    get_runtime_store().save_run_status(run_id, payload)
    if event_type:
        append_run_event(run_id, event_type, status=payload.get("status"), payload=payload)


def store_run_result(run_id: str, result: dict[str, Any]) -> None:
    interrupts = result.get("__interrupt__", [])
    if interrupts:
        store_run_status(
            run_id,
            {
                "status": "pending_approval",
                "approval_status": "pending",
                "interrupts": [getattr(interrupt, "value", interrupt) for interrupt in interrupts],
            },
            event_type="pending_approval",
        )
        return

    final_report = result.get("final_report")
    store_run_status(
        run_id,
        {
            "status": "completed",
            "final_report": final_report.model_dump(mode="json") if final_report else None,
            "approval_status": _serialise_approval_status(result.get("approval_status", "none")),
        },
        event_type="completed",
    )


def mark_run_failed(run_id: str, error: str) -> None:
    store_run_status(
        run_id,
        {"status": "failed", "error": error},
        event_type="failed",
    )


def get_run_status(run_id: str) -> dict[str, Any] | None:
    return get_runtime_store().get_run_status(run_id)


def list_run_events(run_id: str) -> list[dict[str, Any]]:
    return get_runtime_store().list_run_events(run_id)
