"""Reflection agent — quality-gates the synthesis and detects gaps."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import AnswerQuality, CompletenessCheck, DataGap, GapType, ReflectionResult

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("reflection_agent.yaml")

_CONFIDENCE_THRESHOLD = 0.65


class ReflectionAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        analysis = state.get("analysis_result")
        active_domains = state.get("active_domains", [])
        findings = state.get("domain_findings", {})
        query_intent = state.get("query_intent")  # Phase 1

        self.logger.info("Reflection agent running", has_query_intent=query_intent is not None)

        analysis_json = (
            json.dumps(analysis.model_dump(), indent=2, default=str)
            if analysis
            else "No analysis yet."
        )

        # Phase 1 - Add query_intent context if available
        intent_context = ""
        if query_intent:
            intent_context = (
                f"\n\nQuery Intent (structured):\n{json.dumps(query_intent, indent=2, default=str)}\n\n"
                "Validate completeness against this structured intent:\n"
                "- Check if each requested_metric appears in the analysis\n"
                "- Check if requested timeframes are covered\n"
                "- Check if comparison data is present when comparison_intent exists\n"
                "- Populate completeness_check and structured_gaps fields\n"
                "- Set answer_quality based on completeness:\n"
                "  * COMPLETE: All requested elements addressed with high confidence\n"
                "  * PARTIAL: Some elements missing but core question answered\n"
                "  * INSUFFICIENT: Major gaps prevent answering the query"
            )

        messages = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {
                "role": "user",
                "content": (
                    f"Original query: {query}\n\n"
                    f"Active domains required: {active_domains}\n"
                    f"Domains with findings: {list(findings.keys())}\n"
                    f"Confidence threshold: {_CONFIDENCE_THRESHOLD}\n\n"
                    f"Analysis result:\n{analysis_json}\n"
                    f"{intent_context}\n"
                    f"Produce a ReflectionResult JSON assessing quality and gaps."
                ),
            },
        ]

        reflection: ReflectionResult = await self.enforcer.enforce(
            messages=messages,
            output_schema=ReflectionResult,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        # Phase 1 - Perform programmatic completeness validation if query_intent exists
        if query_intent and analysis:
            reflection = self._enhance_with_completeness_check(reflection, query_intent, analysis, findings)

        self.logger.info(
            "Reflection result",
            confidence_ok=reflection.confidence_ok,
            action_needed=reflection.action_needed,
            missing_domains=reflection.missing_domains,
            answer_quality=reflection.answer_quality if query_intent else None,
        )
        return {"reflection_result": reflection}

    def _enhance_with_completeness_check(
        self,
        reflection: ReflectionResult,
        query_intent: dict[str, Any],
        analysis: Any,
        findings: dict[str, Any],
    ) -> ReflectionResult:
        """
        Programmatically validate completeness against query_intent.

        Ensures requested metrics and timeframes are addressed, generates structured
        DataGap objects, and sets answer_quality.
        """
        requested_metrics = query_intent.get("requested_metrics", [])
        temporal_scope = query_intent.get("temporal_scope")
        comparison_intent = query_intent.get("comparison_intent")

        # Extract addressed metrics from analysis
        addressed_metrics = []
        if hasattr(analysis, "addressed_metrics"):
            addressed_metrics = list(analysis.addressed_metrics.keys())
        else:
            # Fallback: check if metrics appear in data_points
            for finding in getattr(analysis, "findings", []):
                for dp in getattr(finding, "data_points", []):
                    metric = getattr(dp, "metric", "").lower()
                    for req_metric in requested_metrics:
                        if req_metric.lower() in metric or metric in req_metric.lower():
                            if req_metric not in addressed_metrics:
                                addressed_metrics.append(req_metric)

        missing_metrics = [m for m in requested_metrics if m not in addressed_metrics]

        # Build CompletenessCheck
        completeness_check = CompletenessCheck(
            requested_metrics=requested_metrics,
            addressed_metrics=addressed_metrics,
            missing_metrics=missing_metrics,
            requested_timeframes=[temporal_scope] if temporal_scope else [],
            covered_timeframes=getattr(analysis, "covered_timeframes", []) if temporal_scope else [],
        )

        # Generate structured DataGap objects for missing metrics
        structured_gaps = list(reflection.structured_gaps) if reflection.structured_gaps else []
        for missing_metric in missing_metrics:
            gap = DataGap(
                gap_type=GapType.UNSUPPORTED_METRIC,
                description=f"Requested metric '{missing_metric}' was not provided in the analysis",
                affected_domains=[],
                severity="moderate",
            )
            structured_gaps.append(gap)

        # Check for comparison data if comparison_intent exists
        if comparison_intent and not getattr(analysis, "comparison_data", None):
            gap = DataGap(
                gap_type=GapType.MISSING_DATA,
                description="Comparison data requested but not provided",
                affected_domains=[],
                severity="critical",
            )
            structured_gaps.append(gap)

        # Determine answer_quality
        if not requested_metrics:
            # No explicit metrics requested, use confidence-based quality
            answer_quality = AnswerQuality.COMPLETE if reflection.confidence_ok else AnswerQuality.PARTIAL
        elif len(missing_metrics) == 0:
            answer_quality = AnswerQuality.COMPLETE
        elif len(missing_metrics) < len(requested_metrics) / 2:
            answer_quality = AnswerQuality.PARTIAL
        else:
            answer_quality = AnswerQuality.INSUFFICIENT

        # Update reflection with Phase 1 fields
        reflection.completeness_check = completeness_check
        reflection.structured_gaps = structured_gaps
        reflection.answer_quality = answer_quality

        return reflection
