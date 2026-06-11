"""Unit tests for the persistent runtime store."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.settings import reset_settings_cache
from infrastructure.runtime_store import get_runtime_store, reset_runtime_store_cache
from models.schemas import ActionProposal, ApprovalRequest, ApprovalResponse, RiskLevel


@pytest.fixture(autouse=True)
def isolated_runtime_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNTIME_STORE_DIR", str(tmp_path / "runtime-store"))
    reset_settings_cache()
    reset_runtime_store_cache()
    yield
    reset_runtime_store_cache()
    reset_settings_cache()


def test_runtime_store_persists_run_status_and_approval_state() -> None:
    store = get_runtime_store()

    proposal = ActionProposal(
        action_name="Emergency Restock",
        tool_name="trigger_emergency_restock",
        tool_args={"sku_id": "SKU-001", "quantity": 25},
        rationale="Inventory is depleted",
        estimated_impact="Restore sellable inventory",
        risk_level=RiskLevel.LOW,
    )
    request = ApprovalRequest(
        run_id="run-store-001",
        proposals=[proposal],
        context_summary="Restock approval required",
    )
    response = ApprovalResponse(
        run_id="run-store-001",
        approved=True,
        approved_action_names=["Emergency Restock"],
    )

    store.save_run_status("run-store-001", {"status": "running"})
    store.save_approval_request(request)
    store.save_approval_response(response)

    reset_runtime_store_cache()
    persisted_store = get_runtime_store()

    assert persisted_store.get_run_status("run-store-001") == {"status": "running"}
    assert persisted_store.get_approval_request("run-store-001") is not None
    assert persisted_store.get_approval_request("run-store-001").context_summary == (
        "Restock approval required"
    )
    assert persisted_store.get_approval_response("run-store-001") is not None
    assert persisted_store.get_approval_response("run-store-001").approved is True

    persisted_store.clear_approval("run-store-001")

    assert persisted_store.get_approval_request("run-store-001") is None
    assert persisted_store.get_approval_response("run-store-001") is None


def test_runtime_store_persists_user_query_history() -> None:
    store = get_runtime_store()

    store.append_user_query(
        "store owner/1",
        {
            "run_id": "run-query-001",
            "query": "Why did sales drop on 2026-05-31?",
            "timestamp": "2026-06-03T00:00:00+00:00",
        },
    )

    reset_runtime_store_cache()
    persisted_store = get_runtime_store()
    history = persisted_store.list_user_queries("store owner/1")

    assert len(history) == 1
    assert history[0]["run_id"] == "run-query-001"
    assert history[0]["query"] == "Why did sales drop on 2026-05-31?"


def test_runtime_store_persists_queued_runs() -> None:
    store = get_runtime_store()

    store.enqueue_run(
        "run-queued-001",
        {"query": "Why did sales drop?", "user_id": "ops_team"},
    )

    claimed = store.claim_next_run("worker-test", stale_after_seconds=60.0)

    assert claimed is not None
    assert claimed["run_id"] == "run-queued-001"
    assert claimed["claimed_by"] == "worker-test"
    assert len(store.list_queued_runs()) == 1

    store.complete_queued_run("run-queued-001")

    assert store.list_queued_runs() == []


def test_runtime_store_persists_action_execution_records() -> None:
    store = get_runtime_store()

    payload = {
        "action_name": "Remove 10 Units From SKU-001",
        "tool_name": "decrease_inventory_quantity",
        "status": "executed",
        "idempotency_key": "idem-001",
        "execution_id": "exec-001",
    }
    store.save_action_execution("run-action-001", "idem-001", payload)

    reset_runtime_store_cache()
    persisted_store = get_runtime_store()

    assert persisted_store.get_action_execution("run-action-001", "idem-001") == payload
