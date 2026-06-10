"""Reflection node — decides whether to loop back or proceed."""
from __future__ import annotations

from typing import Any

import structlog

from models.schemas import IntentType

logger = structlog.get_logger(__name__)

_MAX_REFLECTION_ITERATIONS = 2


def _normalize_domains(domains: list[Any]) -> list[str]:
    normalized = []
    for domain in domains:
        if hasattr(domain, "value"):
            normalized.append(str(domain.value).upper())
        else:
            normalized.append(str(domain).upper())
    return sorted(set(normalized))


def should_reflect(state: dict[str, Any]) -> str:
    """
    Edge routing function for the reflection decision.

    Returns:
        "re_query"      — needs another round of specialist analysis
        "action"        — analysis good; proceed to action executor
        "final_report"  — analysis good; no actions needed
    """
    reflection = state.get("reflection_result")
    iteration = state.get("reflection_iteration", 0)
    analysis = state.get("analysis_result")
    routing = state.get("routing_decision")
    current_domains = _normalize_domains(state.get("active_domains", []))
    prior_domain_sets = [
        _normalize_domains(domain_set)
        for domain_set in state.get("prior_active_domain_sets", [])
    ]

    can_requery = iteration < _MAX_REFLECTION_ITERATIONS

    if not can_requery:
        logger.info(
            "Max reflection iterations reached; proceeding with current evidence",
            iteration=iteration,
        )

    if reflection and can_requery:
        # Phase 1 - Consider answer_quality in addition to missing_domains and confidence
        answer_quality = getattr(reflection, "answer_quality", None)
        needs_requery = (
            bool(reflection.missing_domains)
            or not reflection.confidence_ok
            or (answer_quality == "insufficient")  # Phase 1 - insufficient answers should re-query
        )
        if needs_requery:
            missing_domains = _normalize_domains(list(reflection.missing_domains))
            new_missing_domains = [domain for domain in missing_domains if domain not in current_domains]
            repeated_domain_set = current_domains in prior_domain_sets
            if repeated_domain_set and not new_missing_domains:
                logger.info(
                    "Reflection requested another pass, but routing already repeated with no new domains",
                    current_domains=current_domains,
                    prior_domain_sets=prior_domain_sets,
                )
            else:
                logger.info(
                    "Reflection requested another analysis pass",
                    domains=reflection.missing_domains,
                    confidence_ok=reflection.confidence_ok,
                )
                return "re_query"

    if routing and getattr(routing, "intent", None) == IntentType.REPORT:
        return "action" if getattr(routing, "requires_action", False) else "final_report"

    # Check if actions are required
    requires_action = bool(
        routing and getattr(routing, "requires_action", False)
    ) or bool(
        analysis and getattr(analysis, "recommended_actions", [])
    )

    if requires_action and (reflection is None or reflection.confidence_ok):
        return "action"

    return "final_report"


def build_re_query_update(state: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare state for a re-query iteration.

    Preserve reflection feedback and route back through coordinator for a fresh routing pass.
    """
    reflection = state.get("reflection_result")
    current_iteration = state.get("reflection_iteration", 0)
    current_domains = _normalize_domains(state.get("active_domains", []))
    prior_domain_sets = list(state.get("prior_active_domain_sets", []))
    requery_hints = None

    if reflection is not None:
        # Phase 1 - Include answer_quality and completeness_check in requery hints
        requery_hints = {
            "missing_domains": [domain.value for domain in reflection.missing_domains],
            "confidence_ok": reflection.confidence_ok,
            "gaps": list(reflection.gaps),
            "notes": reflection.notes,
            "previous_active_domains": current_domains,
        }

        # Phase 1 additions
        if hasattr(reflection, "answer_quality") and reflection.answer_quality:
            requery_hints["answer_quality"] = reflection.answer_quality

        if hasattr(reflection, "completeness_check") and reflection.completeness_check:
            requery_hints["missing_metrics"] = reflection.completeness_check.missing_metrics

    if current_domains and current_domains not in prior_domain_sets:
        prior_domain_sets.append(current_domains)

    return {
        "active_domains": [],
        "coordinator_requery_hints": requery_hints,
        "prior_active_domain_sets": prior_domain_sets,
        "reflection_iteration": current_iteration + 1,
        # Clear previous analysis so specialists run fresh
        "domain_findings": {},
        "inventory_items": [],
        "analysis_result": None,
        "reflection_result": None,
    }
