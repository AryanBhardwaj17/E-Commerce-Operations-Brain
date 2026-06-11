"""Unit tests for OutputEnforcer — mocked LLM client."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from models.output_enforcer import OutputEnforcer


class SimpleSchema(BaseModel):
    value: int
    label: str


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def enforcer(mock_llm):
    return OutputEnforcer(mock_llm, max_retries=3)


async def test_enforce_valid_response(enforcer, mock_llm):
    mock_llm.complete.return_value = json.dumps({"value": 42, "label": "test"})
    result = await enforcer.enforce(
        messages=[{"role": "user", "content": "test"}],
        output_schema=SimpleSchema,
    )
    assert result.value == 42
    assert result.label == "test"


async def test_enforce_retries_on_invalid_json(enforcer, mock_llm):
    valid = json.dumps({"value": 1, "label": "ok"})
    mock_llm.complete.side_effect = [
        "not json",       # attempt 1 fails
        "also not json",  # attempt 2 fails
        valid,            # attempt 3 succeeds
    ]
    result = await enforcer.enforce(
        messages=[{"role": "user", "content": "test"}],
        output_schema=SimpleSchema,
    )
    assert result.value == 1
    assert mock_llm.complete.call_count == 3


async def test_enforce_raises_after_max_retries(enforcer, mock_llm):
    mock_llm.complete.return_value = "bad json always"
    with pytest.raises(ValueError, match="Failed to produce valid"):
        await enforcer.enforce(
            messages=[{"role": "user", "content": "test"}],
            output_schema=SimpleSchema,
        )
    assert mock_llm.complete.call_count == 3


async def test_enforce_retries_on_validation_error(enforcer, mock_llm):
    """Missing required field 'label' should trigger retry."""
    invalid = json.dumps({"value": 99})  # missing 'label'
    valid = json.dumps({"value": 99, "label": "fixed"})
    mock_llm.complete.side_effect = [invalid, invalid, valid]

    result = await enforcer.enforce(
        messages=[{"role": "user", "content": "test"}],
        output_schema=SimpleSchema,
    )
    assert result.label == "fixed"
