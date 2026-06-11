"""Unit tests for QueryInterpreterAgent (Phase 1)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, Mock

from src.agents.query_interpreter import QueryInterpreterAgent
from src.core.state import initial_state


@pytest.fixture
def mock_llm_client():
    """Mock LLMClient for testing."""
    client = Mock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def query_interpreter(mock_llm_client):
    """Create QueryInterpreterAgent with mocked LLMClient."""
    return QueryInterpreterAgent(llm_client=mock_llm_client)


@pytest.mark.asyncio
async def test_query_interpreter_parses_single_date_query(query_interpreter, mock_llm_client):
    """Test parsing a single-date diagnostic query."""
    state = initial_state(
        query="Why did revenue drop on May 31st?",
        run_id="test-run-1",
        date_str="2026-05-31",
    )

    # Mock the LLM response
    mock_intent = {
        "temporal_scope": {
            "start_date": "2026-05-31",
            "end_date": "2026-05-31",
            "granularity": "daily",
            "original_phrase": "May 31st"
        },
        "requested_metrics": ["revenue"],
        "comparison_intent": None,
        "response_format": "diagnosis",
        "is_diagnostic": True,
        "confidence": 0.95
    }

    # Mock llm_client.generate to return JSON string
    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    assert "query_intent" in result
    query_intent = result["query_intent"]
    assert query_intent["is_diagnostic"] is True
    assert query_intent["response_format"] == "diagnosis"
    assert query_intent["confidence"] == 0.95
    assert query_intent["temporal_scope"]["start_date"] == "2026-05-31"


@pytest.mark.asyncio
async def test_query_interpreter_parses_date_range_query(query_interpreter, mock_llm_client):
    """Test parsing a query with date range."""
    state = initial_state(
        query="Show me daily sales for the last 7 days",
        run_id="test-run-2",
        date_str="2026-05-31",
    )

    mock_intent = {
        "temporal_scope": {
            "start_date": "2026-05-24",
            "end_date": "2026-05-31",
            "granularity": "daily",
            "original_phrase": "last 7 days"
        },
        "requested_metrics": ["revenue", "order_volume"],
        "comparison_intent": None,
        "response_format": "summary",
        "is_diagnostic": False,
        "confidence": 0.9
    }

    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    assert "query_intent" in result
    query_intent = result["query_intent"]
    assert query_intent["is_diagnostic"] is False
    assert query_intent["response_format"] == "summary"
    assert query_intent["temporal_scope"]["start_date"] == "2026-05-24"
    assert query_intent["temporal_scope"]["end_date"] == "2026-05-31"
    assert query_intent["temporal_scope"]["granularity"] == "daily"


@pytest.mark.asyncio
async def test_query_interpreter_parses_comparison_query(query_interpreter, mock_llm_client):
    """Test parsing a comparison query."""
    state = initial_state(
        query="Compare this week vs last week revenue",
        run_id="test-run-3",
        date_str="2026-05-31",
    )

    mock_intent = {
        "temporal_scope": {
            "start_date": "2026-05-25",
            "end_date": "2026-05-31",
            "granularity": "weekly",
            "original_phrase": "this week"
        },
        "requested_metrics": ["revenue"],
        "comparison_intent": {
            "type": "period_over_period",
            "baseline_period": "previous_week"
        },
        "response_format": "comparison",
        "is_diagnostic": False,
        "confidence": 0.92
    }

    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    assert "query_intent" in result
    query_intent = result["query_intent"]
    assert query_intent["response_format"] == "comparison"
    assert query_intent["comparison_intent"] is not None
    assert query_intent["comparison_intent"]["type"] == "period_over_period"
    assert query_intent["comparison_intent"]["baseline_period"] == "previous_week"


@pytest.mark.asyncio
async def test_query_interpreter_normalizes_invalid_response_format(query_interpreter, mock_llm_client):
    """Test that invalid response_format values are normalized to 'diagnosis'."""
    state = initial_state(
        query="What happened?",
        run_id="test-run-4",
        date_str="2026-05-31",
    )

    mock_intent = {
        "temporal_scope": None,
        "requested_metrics": [],
        "comparison_intent": None,
        "response_format": "invalid_format",  # Invalid value
        "is_diagnostic": True,
        "confidence": 0.7
    }

    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    query_intent = result["query_intent"]
    assert query_intent["response_format"] == "diagnosis"  # Normalized to valid default


@pytest.mark.asyncio
async def test_query_interpreter_handles_missing_temporal_scope(query_interpreter, mock_llm_client):
    """Test handling query with no temporal scope."""
    state = initial_state(
        query="List all low stock items",
        run_id="test-run-5",
        date_str="2026-05-31",
    )

    mock_intent = {
        "temporal_scope": None,
        "requested_metrics": [],
        "comparison_intent": None,
        "response_format": "list",
        "is_diagnostic": False,
        "confidence": 0.95
    }

    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    query_intent = result["query_intent"]
    assert query_intent["temporal_scope"] is None
    assert query_intent["response_format"] == "list"


@pytest.mark.asyncio
async def test_query_interpreter_extracts_multiple_metrics(query_interpreter, mock_llm_client):
    """Test extraction of multiple explicit metrics."""
    state = initial_state(
        query="What's the conversion rate and average order value?",
        run_id="test-run-6",
        date_str="2026-05-31",
    )

    mock_intent = {
        "temporal_scope": {
            "start_date": "2026-05-31",
            "end_date": "2026-05-31",
            "granularity": "daily"
        },
        "requested_metrics": ["conversion_rate", "average_order_value"],
        "comparison_intent": None,
        "response_format": "summary",
        "is_diagnostic": False,
        "confidence": 0.9
    }

    import json
    mock_llm_client.complete = AsyncMock(return_value=json.dumps(mock_intent))

    result = await query_interpreter.run(state)

    query_intent = result["query_intent"]
    assert len(query_intent["requested_metrics"]) == 2
    assert "conversion_rate" in query_intent["requested_metrics"]
    assert "average_order_value" in query_intent["requested_metrics"]
