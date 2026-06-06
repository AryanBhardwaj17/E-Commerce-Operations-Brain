"""Query Interpreter agent — parses natural language queries into structured intent."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("query_interpreter.yaml")


class QueryInterpreterAgent(BaseAgent):
    """
    Parses natural language queries into structured query intent.

    Responsibilities:
    - Parse relative dates into absolute date ranges
    - Extract explicitly mentioned metrics
    - Detect temporal granularity (daily/weekly/monthly)
    - Classify comparison patterns
    - Determine appropriate response format
    """

    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        date_str = state["date_str"]
        self.logger.info("Query interpreter parsing query", query=query, reference_date=date_str)

        # Parse reference date for relative date calculations
        try:
            reference_date = datetime.fromisoformat(date_str)
        except ValueError:
            reference_date = datetime.now()

        messages = [
            {
                "role": "system",
                "content": self.config.system_prompt or "",
            },
            {
                "role": "user",
                "content": (
                    f"Business query: {query}\n\n"
                    f"Reference date for relative calculations: {date_str}\n\n"
                    f"Parse this query into structured QueryIntent. Extract:\n"
                    f"1. Temporal scope (dates, granularity)\n"
                    f"2. Requested metrics (explicit mentions only)\n"
                    f"3. Comparison intent (if present)\n"
                    f"4. Appropriate response format\n"
                    f"5. Is this diagnostic vs reporting?\n\n"
                    f"Return a JSON object with this structure:\n"
                    f"{{\n"
                    f"  \"temporal_scope\": {{\"start_date\": \"YYYY-MM-DD\", \"end_date\": \"YYYY-MM-DD\", \"granularity\": \"daily\"}},\n"
                    f"  \"requested_metrics\": [\"revenue\", \"order_volume\"],\n"
                    f"  \"comparison_intent\": {{\"type\": \"period_over_period\", \"baseline_period\": \"previous_week\"}},\n"
                    f"  \"response_format\": \"summary\",\n"
                    f"  \"is_diagnostic\": false,\n"
                    f"  \"confidence\": 0.85\n"
                    f"}}\n"
                    f"Respond with ONLY the JSON object, no other text."
                ),
            },
        ]

        # Call LLM to get JSON response
        response_text = await self.llm_client.complete(
            messages=messages,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Parse JSON from response
        try:
            # Extract JSON from response (may have markdown code blocks)
            response_str = str(response_text).strip()
            if "```json" in response_str:
                # Extract from markdown code block
                start = response_str.find("```json") + 7
                end = response_str.find("```", start)
                response_str = response_str[start:end].strip()
            elif "```" in response_str:
                # Extract from generic code block
                start = response_str.find("```") + 3
                end = response_str.find("```", start)
                response_str = response_str[start:end].strip()

            query_intent_raw = json.loads(response_str)
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            # Fallback to empty intent if parsing fails
            self.logger.warning(f"Failed to parse query intent JSON: {e}, using defaults")
            query_intent_raw = {
                "temporal_scope": None,
                "requested_metrics": [],
                "comparison_intent": None,
                "response_format": "diagnosis",
                "is_diagnostic": True,
                "confidence": 0.5,
            }

        # Validate and normalize the query intent
        query_intent = self._normalize_query_intent(query_intent_raw, reference_date)

        self.logger.info(
            "Query intent parsed",
            confidence=query_intent.get("confidence"),
            is_diagnostic=query_intent.get("is_diagnostic"),
            response_format=query_intent.get("response_format"),
            has_temporal_scope=query_intent.get("temporal_scope") is not None,
        )

        return {"query_intent": query_intent}

    def _normalize_query_intent(self, raw_intent: dict[str, Any], reference_date: datetime) -> dict[str, Any]:
        """
        Normalize and validate query intent structure.

        Ensures temporal_scope has absolute dates, validates response_format values,
        and provides sensible defaults for missing fields.
        """
        normalized = {
            "temporal_scope": raw_intent.get("temporal_scope"),
            "requested_metrics": raw_intent.get("requested_metrics", []),
            "comparison_intent": raw_intent.get("comparison_intent"),
            "response_format": raw_intent.get("response_format", "diagnosis"),
            "is_diagnostic": raw_intent.get("is_diagnostic", False),
            "confidence": raw_intent.get("confidence", 0.5),
        }

        # Normalize response_format to valid enum values
        valid_formats = {"diagnosis", "summary", "comparison", "list"}
        if normalized["response_format"] not in valid_formats:
            normalized["response_format"] = "diagnosis"

        # Ensure temporal_scope has absolute dates if present
        if temporal_scope := normalized.get("temporal_scope"):
            if not temporal_scope.get("start_date"):
                # Default to reference date if no start_date
                temporal_scope["start_date"] = reference_date.strftime("%Y-%m-%d")

            # If no end_date, make it same as start_date (single-day query)
            if not temporal_scope.get("end_date"):
                temporal_scope["end_date"] = temporal_scope["start_date"]

            # Default granularity
            if not temporal_scope.get("granularity"):
                temporal_scope["granularity"] = "daily"

        return normalized
