"""Unit tests for execution backend selection and queued worker processing."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.run_state import get_run_status, list_run_events
from core.settings import reset_settings_cache
from execution.query_runner import (
    QueuedRunWorker,
    execute_submitted_run,
    get_query_runner,
    reset_query_runner_cache,
)
from infrastructure.runtime_store import reset_runtime_store_cache
from models.schemas import FinalReport


@pytest.fixture(autouse=True)
def isolated_execution_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNTIME_STORE_DIR", str(tmp_path / "runtime-store"))
    reset_settings_cache()
    reset_runtime_store_cache()
    reset_query_runner_cache()
    yield
    reset_query_runner_cache()
    reset_runtime_store_cache()
    reset_settings_cache()


def test_get_query_runner_uses_queued_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_BACKEND", "queued")
    reset_settings_cache()
    reset_query_runner_cache()

    runner = get_query_runner()

    assert runner.__class__.__name__ == "QueuedQueryRunner"


@pytest.mark.asyncio
async def test_queued_worker_processes_claimed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_BACKEND", "queued")
    reset_settings_cache()
    reset_query_runner_cache()

    runner = get_query_runner()

    async def fake_execute(run_id: str, state: dict[str, object]) -> None:
        report = FinalReport(
            run_id=run_id,
            query=str(state["query"]),
            executive_summary="Processed by queued worker",
            confidence_score=0.88,
        )
        from core.run_state import store_run_result  # noqa: PLC0415

        store_run_result(run_id, {"final_report": report, "approval_status": "none"})

    monkeypatch.setattr("execution.query_runner.execute_submitted_run", fake_execute)

    runner.submit(
        "run-worker-001",
        {"query": "Why did sales drop?", "user_id": "ops_team"},
    )

    worker = QueuedRunWorker(worker_id="worker-test", poll_interval_seconds=0.01)
    processed = await worker.run_once()

    assert processed is True
    status = get_run_status("run-worker-001")
    assert status is not None
    assert status["status"] == "completed"
    assert status["final_report"]["executive_summary"] == "Processed by queued worker"


@pytest.mark.asyncio
async def test_execute_submitted_run_retries_transient_graph_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    class FakeGraph:
        async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, object]:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary transport failure")
            report = FinalReport(
                run_id=str(state["run_id"]),
                query=str(state["query"]),
                executive_summary="Recovered after retry",
                confidence_score=0.92,
            )
            return {"final_report": report, "approval_status": "none"}

    async def fake_get_runtime_graph() -> FakeGraph:
        return FakeGraph()

    monkeypatch.setattr("execution.query_runner.get_runtime_graph", fake_get_runtime_graph)

    await execute_submitted_run(
        "run-retry-001",
        {"run_id": "run-retry-001", "query": "Why did sales drop?", "user_id": "ops_team"},
    )

    status = get_run_status("run-retry-001")
    events = list_run_events("run-retry-001")

    assert attempts["count"] == 2
    assert status is not None
    assert status["status"] == "completed"
    assert status["final_report"]["executive_summary"] == "Recovered after retry"
    assert any(event["type"] == "runner_retry_scheduled" for event in events)
