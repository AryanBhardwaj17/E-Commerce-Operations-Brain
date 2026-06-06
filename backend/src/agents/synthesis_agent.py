"""Synthesis agent — produces cross-domain root-cause analysis."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import AnalysisResult

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("synthesis_agent.yaml")


def _memory_summary(memory_ctx: Any) -> str:
    if not memory_ctx:
        return "No prior memory context."

    summary_parts: list[str] = []
    if getattr(memory_ctx, "kedb_matches", None):
        summary_parts.append(f"KEDB matches: {len(memory_ctx.kedb_matches)}")
    if getattr(memory_ctx, "kadb_matches", None):
        summary_parts.append(f"KADB matches: {len(memory_ctx.kadb_matches)}")

    return "; ".join(summary_parts) if summary_parts else "No prior memory context."


class SynthesisAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        findings = state.get("domain_findings", {})
        memory_ctx = state.get("memory_context")
        query_intent = state.get("query_intent")  # Phase 1

        self.logger.info(
            "Synthesis agent running",
            domain_count=len(findings),
            has_query_intent=query_intent is not None,
        )

        findings_json = json.dumps(
            {k: v.model_dump() for k, v in findings.items()},
            indent=2,
            default=str,
        )

        memory_summary = _memory_summary(memory_ctx)
        kedb_summary = (
            json.dumps(list(memory_ctx.kedb_matches), indent=2, default=str)
            if memory_ctx and memory_ctx.kedb_matches
            else "None"
        )

        # Phase 1 - Add query_intent context if available
        intent_context = ""
        if query_intent:
            response_format = query_intent.get("response_format", "diagnosis")
            requested_metrics = query_intent.get("requested_metrics", [])
            comparison_intent = query_intent.get("comparison_intent")

            intent_context = (
                f"\n\nQuery Intent (structured):\n{json.dumps(query_intent, indent=2, default=str)}\n\n"
                f"Structure your answer according to response_format='{response_format}':\n"
            )

            if response_format == "diagnosis":
                intent_context += "- Provide root-cause analysis with evidence\n- Use narrative format\n"
            elif response_format == "summary":
                intent_context += "- Provide high-level overview of key findings\n- Use concise bullet-style summaries\n"
            elif response_format == "comparison":
                intent_context += "- Provide side-by-side comparison\n- Populate comparison_data with before/after values\n"
            elif response_format == "list":
                intent_context += "- Structure as item listing\n- Focus on enumeration rather than analysis\n"

            if requested_metrics:
                intent_context += f"\nPopulate addressed_metrics dict with these metrics: {requested_metrics}\n"

            if comparison_intent:
                intent_context += "Populate comparison_data with comparison results.\n"

            intent_context += "Populate covered_timeframes with the periods analyzed.\n"

        messages = [
            {"role": "system", "content": self.config.system_prompt or ""},
            {
                "role": "user",
                "content": (
                    f"Original query: {query}\n\n"
                    f"Memory context:\n{memory_summary}\n\n"
                    f"KEDB similar incidents:\n{kedb_summary}\n\n"
                    f"Domain findings:\n{findings_json}\n"
                    f"{intent_context}\n"
                    f"Synthesise these findings into an AnalysisResult JSON."
                ),
            },
        ]

        analysis: AnalysisResult = await self.enforcer.enforce(
            messages=messages,
            output_schema=AnalysisResult,
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        # Phase 1 - Populate response_format if query_intent provided
        if query_intent and hasattr(analysis, "response_format"):
            from models.schemas import ResponseFormat
            response_format_str = query_intent.get("response_format", "diagnosis")
            try:
                analysis.response_format = ResponseFormat(response_format_str)
            except ValueError:
                analysis.response_format = ResponseFormat.DIAGNOSIS

        self.logger.info(
            "Synthesis complete",
            confidence=analysis.confidence_score,
            is_new_pattern=analysis.is_new_pattern,
            response_format=analysis.response_format if query_intent else None,
        )
        return {"analysis_result": analysis}
