"""Unit tests for the memory-recall answer path.

Covers the deterministic recall detector, the FinalReport formatter, and the
coordinator/graph routing decision — all without ChromaDB or an LLM.
"""
from __future__ import annotations

import pytest

from core.memory_intent import is_memory_recall_request
from core.memory_response import build_memory_recall_report
from models.schemas import IntentType, MemoryContext, ReportKind

# ── Detector ────────────────────────────────────────────────────────────────

class TestMemoryRecallDetector:
    @pytest.mark.parametrize(
        "query",
        [
            "Which actions worked best in past incidents?",
            "What did we do last time sales dropped like this?",
            "Has this happened before?",
            "Did discounts help previously?",
            "What worked best last time?",
            "How have we handled this in the past?",
            "Historically, which campaigns recovered fastest?",
        ],
    )
    def test_recall_queries_detected(self, query: str):
        assert is_memory_recall_request(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "Why did sales drop yesterday?",
            "Summarize yesterday's business health.",
            "Fix the issue.",
            "Restock affected products.",
            "Which products are close to stock-out?",
            "Run a 10% discount on top 3 products.",
            "",
        ],
    )
    def test_non_recall_queries_not_detected(self, query: str):
        assert is_memory_recall_request(query) is False


# ── Formatter ───────────────────────────────────────────────────────────────

class TestMemoryRecallReport:
    def test_report_ranks_actions_with_outcomes(self):
        memory_context = MemoryContext(
            kedb_matches=[
                {
                    "title": "Sales drop from stockout",
                    "root_cause": "Stockout of high-demand SKUs",
                    "recommended_actions": ["trigger_emergency_restock", "send_customer_notification"],
                    "occurrence_count": 4,
                    "outcome": "Restock + notification recovered 65% of lost revenue in 72h.",
                },
                {
                    "title": "Flash discount recovery",
                    "recommended_actions": ["apply_discount_code"],
                    "occurrence_count": 5,
                    "resolution": "20% discount recovered 82% of revenue in 48h.",
                },
            ],
            kadb_matches=[
                {
                    "title": "Flash Discount Recovery Playbook",
                    "artifact_type": "playbook",
                    "content": "Apply 15-20% discount for 48h; expect 70-85% recovery.",
                }
            ],
        )

        report = build_memory_recall_report(
            run_id="run-1",
            query="Which actions worked best in past incidents?",
            memory_context=memory_context,
        )

        assert report.report_kind == ReportKind.HISTORY_RESPONSE
        assert report.intent == IntentType.MEMORY
        assert report.memory_context_used is True
        assert report.confidence_score >= 0.7
        # Outcomes surfaced in the narrative
        assert "82% of revenue" in report.executive_summary
        assert "Flash Discount Recovery Playbook" in report.executive_summary
        # Distinct actions aggregated, order preserved
        assert report.recommendations == [
            "trigger_emergency_restock",
            "send_customer_notification",
            "apply_discount_code",
        ]

    def test_empty_memory_is_handled_gracefully(self):
        report = build_memory_recall_report(
            run_id="run-2",
            query="Has this happened before?",
            memory_context=MemoryContext(),
        )
        assert report.report_kind == ReportKind.HISTORY_RESPONSE
        assert report.intent == IntentType.MEMORY
        assert report.memory_context_used is False
        assert "no closely matching past records" in report.executive_summary.lower()

    def test_none_memory_context_does_not_crash(self):
        report = build_memory_recall_report(
            run_id="run-3",
            query="What did we do last time?",
            memory_context=None,
        )
        assert report.memory_context_used is False

    def test_comma_delimited_actions_are_split(self):
        memory_context = MemoryContext(
            kedb_matches=[{"title": "Incident", "recommended_actions": "resume_campaign, apply_discount_code"}],
        )
        report = build_memory_recall_report(
            run_id="run-4",
            query="What worked last time?",
            memory_context=memory_context,
        )
        assert report.recommendations == ["resume_campaign", "apply_discount_code"]


# ── Memory agent (deterministic build, no LLM) ────────────────────────────────

class TestMemoryAgentDeterministicBuild:
    async def test_builds_context_without_llm_and_trims_long_fields(self):
        from unittest.mock import Mock

        from agents.memory_agent import MemoryAgent
        from application.repositories import (
            configure_repository_registry,
            reset_repository_registry,
        )
        from bootstrap.tools import initialize_tool_registry
        from infrastructure.repositories.mock.factory import build_mock_repository_registry

        reset_repository_registry()
        configure_repository_registry(build_mock_repository_registry())
        initialize_tool_registry()

        # LLM client must never be called — fail loudly if the agent tries.
        llm = Mock()
        llm.complete.side_effect = AssertionError("memory_agent must not call the LLM")
        agent = MemoryAgent(llm)

        big = "X" * 3000
        agent.call_tool = lambda name, **kwargs: (
            [{"error_code": "E1", "title": "Discount recovery",
              "recommended_actions": ["apply_discount_code"], "document": big}]
            if name == "search_kedb"
            else [{"id": "kadb-1", "title": "Outcome log", "content": big}]
        )

        result = await agent.run({"query": "Which actions worked best in past incidents?"})
        memory_ctx = result["memory_context"]

        assert len(memory_ctx.kedb_matches) == 1
        assert len(memory_ctx.kadb_matches) == 1
        # Long free-text fields are trimmed so downstream prompts stay bounded.
        assert len(memory_ctx.kedb_matches[0]["document"]) <= 801
        assert len(memory_ctx.kadb_matches[0]["content"]) <= 801
        # Structured fields pass through untouched.
        assert memory_ctx.kedb_matches[0]["recommended_actions"] == ["apply_discount_code"]

        reset_repository_registry()


# ── Coordinator routing ───────────────────────────────────────────────────────

class TestCoordinatorMemoryRouting:
    async def test_coordinator_routes_recall_query_to_memory_intent(self):
        from unittest.mock import Mock

        from agents.coordinator import CoordinatorAgent

        agent = CoordinatorAgent(Mock())
        state = {
            "query": "Which actions worked best in past incidents?",
            "run_id": "run-5",
            "user_id": "ops_team",
            "coordinator_requery_hints": None,
            "query_intent": None,
        }

        result = await agent.run(state)

        routing = result["routing_decision"]
        assert routing.intent == IntentType.MEMORY
        assert routing.active_domains == []
        assert routing.requires_action is False
        assert result["active_domains"] == []
