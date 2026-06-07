"""Render recalled memory (KEDB/KADB) into a FinalReport for memory-recall queries.

This is the answer path for "Learning From the Past" questions. The memory agent has
already populated ``memory_context`` from the knowledge bases; here we deterministically
format those matches into a structured, readable report — without running a fresh
diagnostic or proposing/executing any actions.
"""
from __future__ import annotations

from typing import Any

from models.schemas import FinalReport, IntentType, MemoryContext, ReportKind


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _string_list(value: Any) -> list[str]:
    """Coerce a field that may be a list or comma/space-delimited string into a list."""
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    text = _as_text(value)
    if not text:
        return []
    # Tolerate "a, b, c" or "a,b,c"
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _first_present(match: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _as_text(match.get(key))
        if text:
            return text
    return ""


def _format_kedb_match(match: dict[str, Any]) -> str:
    title = _first_present(match, "title", "error_code") or "Past incident"
    root_cause = _first_present(match, "root_cause")
    outcome = _first_present(match, "outcome", "resolution", "document", "description")
    occurrences = match.get("occurrence_count")
    actions = _string_list(match.get("recommended_actions"))

    parts = [f"**{title}**"]
    if root_cause and root_cause.lower() not in {"n/a", "n/a — this is a successful recovery pattern"}:
        parts.append(f"Root cause: {root_cause}.")
    if occurrences:
        parts.append(f"Seen {occurrences} time(s) before.")
    if outcome:
        parts.append(f"What we did / outcome: {outcome[:400]}")
    if actions:
        parts.append(f"Actions used: {', '.join(actions)}.")
    return " ".join(parts)


def _format_kadb_match(match: dict[str, Any]) -> str:
    title = _first_present(match, "title", "id") or "Playbook"
    artifact_type = _first_present(match, "artifact_type")
    content = _first_present(match, "content", "document")

    header = f"**{title}**"
    if artifact_type:
        header += f" ({artifact_type})"
    if content:
        return f"{header}: {content[:400]}"
    return header


def _collect_recommended_actions(kedb_matches: list[dict[str, Any]]) -> list[str]:
    """Aggregate distinct recommended actions across recalled incidents, preserving order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for match in kedb_matches:
        for action in _string_list(match.get("recommended_actions")):
            key = action.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(action)
    return ordered


def build_memory_recall_report(
    *,
    run_id: str,
    query: str,
    memory_context: MemoryContext | None,
    intent: IntentType | None = None,
) -> FinalReport:
    """Build a FinalReport that answers a memory-recall question from KEDB/KADB matches."""
    kedb_matches = list(memory_context.kedb_matches) if memory_context else []
    kadb_matches = list(memory_context.kadb_matches) if memory_context else []

    if not kedb_matches and not kadb_matches:
        return FinalReport(
            run_id=run_id,
            query=query,
            report_kind=ReportKind.HISTORY_RESPONSE,
            intent=intent or IntentType.MEMORY,
            memory_context_used=False,
            executive_summary=(
                "I searched our incident history (KEDB) and operational playbooks (KADB) but "
                "found no closely matching past records for this question. If the knowledge bases "
                "were recently updated, they may need to be re-seeded before historical recall works."
            ),
            recommendations=[
                "Try naming the specific symptom or domain (e.g. 'sales drop from stockout', "
                "'paused campaign recovery').",
            ],
            confidence_score=0.4,
        )

    summary_lines: list[str] = []
    if kedb_matches:
        summary_lines.append(
            f"Found {len(kedb_matches)} similar past incident(s) in our history:"
        )
        summary_lines.extend(f"- {_format_kedb_match(match)}" for match in kedb_matches)
    if kadb_matches:
        if summary_lines:
            summary_lines.append("")
        summary_lines.append(
            f"Relevant playbooks and recorded outcomes ({len(kadb_matches)}):"
        )
        summary_lines.extend(f"- {_format_kadb_match(match)}" for match in kadb_matches)

    executive_summary = "\n".join(summary_lines)

    recommendations = _collect_recommended_actions(kedb_matches)
    if not recommendations:
        recommendations = [
            "Review the recalled playbooks above and apply the steps that match the current situation."
        ]

    return FinalReport(
        run_id=run_id,
        query=query,
        report_kind=ReportKind.HISTORY_RESPONSE,
        intent=intent or IntentType.MEMORY,
        memory_context_used=True,
        executive_summary=executive_summary,
        recommendations=recommendations,
        confidence_score=0.8,
    )
