"""Unit tests for deterministic query guardrails."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.guardrails import evaluate_query_guardrails
from core.run_state import record_submitted_query
from core.settings import reset_settings_cache
from core.state import initial_state
from infrastructure.runtime_store import reset_runtime_store_cache
from models.schemas import IntentType, ReportKind


@pytest.fixture(autouse=True)
def isolated_runtime_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNTIME_STORE_DIR", str(tmp_path / "runtime-store"))
    reset_settings_cache()
    reset_runtime_store_cache()
    yield
    reset_runtime_store_cache()
    reset_settings_cache()


def test_guardrails_return_first_question_from_history() -> None:
    record_submitted_query(
        "run-history-001",
        "store_owner",
        "Why did sales drop on 2026-05-31?",
        "2026-05-31",
    )
    record_submitted_query(
        "run-history-002",
        "store_owner",
        "List all inventory items for 2026-06-03.",
        "2026-06-03",
    )

    report = evaluate_query_guardrails(
        initial_state(
            query="What was the first question that I asked it?",
            run_id="run-history-003",
            user_id="store_owner",
        )
    )

    assert report is not None
    assert report.intent == IntentType.MEMORY
    assert report.report_kind == ReportKind.HISTORY_RESPONSE
    assert "Why did sales drop on 2026-05-31?" in report.executive_summary


def test_guardrails_block_non_business_prompt() -> None:
    report = evaluate_query_guardrails(
        initial_state(
            query="Write a poem on sky.",
            run_id="run-guardrail-001",
            user_id="store_owner",
        )
    )

    assert report is not None
    assert report.intent == IntentType.OUT_OF_SCOPE
    assert report.report_kind == ReportKind.OUT_OF_SCOPE
    assert "store operations" in report.executive_summary.lower()
    assert report.recommendations


def test_guardrails_allow_business_query_to_continue() -> None:
    report = evaluate_query_guardrails(
        initial_state(
            query="Why did sales drop on 2026-05-31?",
            run_id="run-guardrail-002",
            user_id="store_owner",
        )
    )

    assert report is None
