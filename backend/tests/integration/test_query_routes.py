"""Integration tests for query submission and durable event history."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import query as query_routes
from application.repositories import reset_repository_registry
from core.run_state import store_run_result
from core.settings import reset_settings_cache
from execution.query_runner import reset_query_runner_cache
from infrastructure.runtime_store import get_runtime_store, reset_runtime_store_cache
from models.schemas import FinalReport


class ImmediateQueryRunner:
    def submit(self, run_id: str, state: dict) -> None:
        report = FinalReport(
            run_id=run_id,
            query=state["query"],
            executive_summary="Completed immediately for test",
            confidence_score=0.9,
        )
        store_run_result(run_id, {"final_report": report, "approval_status": "none"})

    async def shutdown(self) -> None:
        return None


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RUNTIME_STORE_DIR", str(tmp_path / "runtime-store"))
    reset_repository_registry()
    reset_settings_cache()
    reset_runtime_store_cache()
    reset_query_runner_cache()
    yield
    reset_repository_registry()
    reset_query_runner_cache()
    reset_runtime_store_cache()
    reset_settings_cache()


def test_submit_query_persists_status_and_events(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(query_routes.router)

    monkeypatch.setattr(query_routes, "get_query_runner", lambda: ImmediateQueryRunner())

    with TestClient(app) as client:
        response = client.post(
            "/query",
            json={"query": "Why did sales drop on 2026-05-31?"},
        )

        assert response.status_code == 200
        payload = response.json()
        run_id = payload["run_id"]

        status = client.get(f"/query/{run_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "completed"
        assert status.json()["final_report"]["report_kind"] == "analysis"
        assert status.json()["final_report"]["executive_summary"] == "Completed immediately for test"

        events = client.get(f"/query/{run_id}/events")
        assert events.status_code == 200
        event_types = [event["type"] for event in events.json()["events"]]
        assert "accepted" in event_types
        assert "completed" in event_types

        history = get_runtime_store().list_user_queries("ops_team")
        assert len(history) == 1
        assert history[0]["query"] == "Why did sales drop on 2026-05-31?"


def test_submit_query_reuses_matching_inflight_non_mutating_run(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(query_routes.router)

    submissions: list[str] = []

    class TrackingRunner:
        def submit(self, run_id: str, state: dict) -> None:
            submissions.append(run_id)

        async def shutdown(self) -> None:
            return None

    runner = TrackingRunner()
    monkeypatch.setattr(query_routes, "get_query_runner", lambda: runner)

    with TestClient(app) as client:
        first = client.post(
            "/query",
            json={"query": "Why did sales drop on 2026-05-31?", "user_id": "ops_team"},
        )
        second = client.post(
            "/query",
            json={"query": "Why did sales drop on 2026-05-31?", "user_id": "ops_team"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["run_id"] == second.json()["run_id"]
        assert len(submissions) == 1

        events = client.get(f"/query/{first.json()['run_id']}/events")
        event_types = [event["type"] for event in events.json()["events"]]
        assert "duplicate_query_reused" in event_types


def test_submit_query_does_not_reuse_direct_inventory_mutation_run(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(query_routes.router)

    submissions: list[str] = []

    class TrackingRunner:
        def submit(self, run_id: str, state: dict) -> None:
            submissions.append(run_id)

        async def shutdown(self) -> None:
            return None

    runner = TrackingRunner()
    monkeypatch.setattr(query_routes, "get_query_runner", lambda: runner)

    with TestClient(app) as client:
        first = client.post(
            "/query",
            json={"query": "Remove 10 units from SKU-001", "user_id": "ops_team"},
        )
        second = client.post(
            "/query",
            json={"query": "Remove 10 units from SKU-001", "user_id": "ops_team"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["run_id"] != second.json()["run_id"]
        assert len(submissions) == 2


def test_submit_query_rejects_blank_input(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(query_routes.router)

    submit_called = False

    class TrackingRunner:
        def submit(self, run_id: str, state: dict) -> None:
            nonlocal submit_called
            submit_called = True

        async def shutdown(self) -> None:
            return None

    monkeypatch.setattr(query_routes, "get_query_runner", lambda: TrackingRunner())

    with TestClient(app) as client:
        response = client.post("/query", json={"query": "   "})

        assert response.status_code == 400
        assert response.json()["detail"] == "Query cannot be empty."
        assert submit_called is False
