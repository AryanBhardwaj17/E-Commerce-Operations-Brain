"""Extended tests for guardrails with memory and summary queries."""
from __future__ import annotations

from core.guardrails import evaluate_query_guardrails
from models.schemas import IntentType, ReportKind


class TestMemoryQueries:
    """Test that memory-related queries pass guardrails."""

    def test_past_incidents_query_passes_guardrails(self):
        """Test that queries about past incidents are accepted."""
        state = {
            "query": "Which actions worked best in past incidents?",
            "user_id": "test_user",
            "run_id": "test_run_001",
        }

        result = evaluate_query_guardrails(state)

        # Should pass guardrails (return None to continue processing)
        assert result is None

    def test_incident_history_query_passes_guardrails(self):
        """Test that historical incident queries are accepted."""
        state = {
            "query": "What happened in previous incidents?",
            "user_id": "test_user",
            "run_id": "test_run_002",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_action_history_query_passes_guardrails(self):
        """Test that action history queries are accepted."""
        state = {
            "query": "Show me the actions taken in the past",
            "user_id": "test_user",
            "run_id": "test_run_003",
        }

        result = evaluate_query_guardrails(state)
        assert result is None


class TestSummaryQueries:
    """Test that summary and reporting queries pass guardrails."""

    def test_business_health_summary_passes_guardrails(self):
        """Test that business health summary queries are accepted."""
        state = {
            "query": "Summarize yesterday's business health",
            "user_id": "test_user",
            "run_id": "test_run_004",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_daily_summary_passes_guardrails(self):
        """Test that daily summary queries are accepted."""
        state = {
            "query": "Give me a summary of today's performance",
            "user_id": "test_user",
            "run_id": "test_run_005",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_business_overview_passes_guardrails(self):
        """Test that business overview queries are accepted."""
        state = {
            "query": "What's the business overview for this week?",
            "user_id": "test_user",
            "run_id": "test_run_006",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_metrics_summary_passes_guardrails(self):
        """Test that metrics summary queries are accepted."""
        state = {
            "query": "Show me the key metrics for yesterday",
            "user_id": "test_user",
            "run_id": "test_run_007",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_kpi_report_passes_guardrails(self):
        """Test that KPI report queries are accepted."""
        state = {
            "query": "Generate a KPI report for last month",
            "user_id": "test_user",
            "run_id": "test_run_008",
        }

        result = evaluate_query_guardrails(state)
        assert result is None


class TestPerformanceQueries:
    """Test that performance-related queries pass guardrails."""

    def test_performance_query_passes_guardrails(self):
        """Test that performance queries are accepted."""
        state = {
            "query": "How was the performance yesterday?",
            "user_id": "test_user",
            "run_id": "test_run_009",
        }

        result = evaluate_query_guardrails(state)
        assert result is None

    def test_historical_performance_passes_guardrails(self):
        """Test that historical performance queries are accepted."""
        state = {
            "query": "Show me historical performance trends",
            "user_id": "test_user",
            "run_id": "test_run_010",
        }

        result = evaluate_query_guardrails(state)
        assert result is None


class TestNonBusinessQueries:
    """Test that non-business queries are still blocked."""

    def test_weather_query_blocked(self):
        """Test that weather queries are blocked."""
        state = {
            "query": "What's the weather like?",
            "user_id": "test_user",
            "run_id": "test_run_011",
        }

        result = evaluate_query_guardrails(state)
        assert result is not None
        assert result.report_kind == ReportKind.OUT_OF_SCOPE
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_general_question_blocked(self):
        """Test that general questions are blocked."""
        state = {
            "query": "Tell me a joke",
            "user_id": "test_user",
            "run_id": "test_run_012",
        }

        result = evaluate_query_guardrails(state)
        assert result is not None
        assert result.report_kind == ReportKind.OUT_OF_SCOPE

    def test_empty_query_blocked(self):
        """Test that empty queries are blocked."""
        state = {
            "query": "",
            "user_id": "test_user",
            "run_id": "test_run_013",
        }

        result = evaluate_query_guardrails(state)
        assert result is not None
        assert result.report_kind == ReportKind.OUT_OF_SCOPE
