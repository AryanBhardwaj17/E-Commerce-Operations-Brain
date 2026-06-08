"""Deterministic pre-routing guardrails for unsupported and recall-style prompts."""
from __future__ import annotations

import re
from typing import Any

from core.run_state import list_user_query_history
from models.schemas import FinalReport, IntentType, ReportKind

_BUSINESS_HINTS = {
    "sales",
    "revenue",
    "profit",
    "margin",
    "inventory",
    "stock",
    "stockout",
    "restock",
    "reorder",
    "sku",
    "item",
    "items",
    "product",
    "products",
    "catalog",
    "marketing",
    "campaign",
    "promotion",
    "discount",
    "traffic",
    "conversion",
    "customer",
    "customers",
    "support",
    "refund",
    "returns",
    "review",
    "reviews",
    "complaint",
    "complaints",
    "order",
    "orders",
    "checkout",
    "store",
    "shop",
    "gmv",
    "aov",
    "category",
    "categories",
    "demand",
    # Memory and historical context keywords
    "action",
    "actions",
    "incident",
    "incidents",
    "past",
    "previous",
    "history",
    "historical",
    # Summary and reporting keywords
    "business",
    "health",
    "summary",
    "summarize",
    "summarise",
    "overview",
    "report",
    "yesterday",
    "today",
    "week",
    "month",
    "performance",
    "metrics",
    "kpi",
    "kpis",
}

_FIRST_QUESTION_PATTERN = re.compile(
    r"\b(first question|first thing i asked|what was the first question)\b",
)
_PREVIOUS_QUESTION_PATTERN = re.compile(
    r"\b(last question|previous question|question before this|asked before this|what did i ask before|what was my last question|what was the last question)\b",
)
_RECENT_QUESTIONS_PATTERN = re.compile(
    r"\b(recent questions|list (all )?(my )?questions|what have i asked|questions i asked|show (me )?(my )?questions)\b",
)


def evaluate_query_guardrails(state: dict[str, Any]) -> FinalReport | None:
    query = _normalise_query(state.get("query", ""))
    if not query:
        return build_non_business_report(
            run_id=state["run_id"],
            query="",
            summary=(
                "Please enter a store operations question. I can help with sales, inventory, "
                "marketing, and support questions."
            ),
        )

    history_report = _build_history_report(
        query=query,
        user_id=state["user_id"],
        run_id=state["run_id"],
    )
    if history_report is not None:
        return history_report

    if not _looks_business_related(query):
        return build_non_business_report(run_id=state["run_id"], query=query)

    return None


def build_non_business_report(run_id: str, query: str, summary: str | None = None) -> FinalReport:
    return FinalReport(
        run_id=run_id,
        query=query,
        report_kind=ReportKind.OUT_OF_SCOPE,
        intent=IntentType.OUT_OF_SCOPE,
        executive_summary=(
            summary
            or "I can help with store operations questions about sales, inventory, marketing, and support."
        ),
        recommendations=[
            "Ask about a business outcome, metric, or operational issue you want investigated.",
            "Include the domain when possible, for example sales, inventory, marketing, or support.",
            "Example: 'Why did sales drop on 2026-05-31?' or 'List all inventory items for 2026-06-03.'",
        ],
        confidence_score=1.0,
    )


def _build_history_report(query: str, user_id: str, run_id: str) -> FinalReport | None:
    lowered_query = query.lower()
    if not _is_history_request(lowered_query):
        return None

    history = [
        entry
        for entry in list_user_query_history(user_id)
        if entry.get("run_id") != run_id and entry.get("query")
    ]

    if not history:
        summary = "I don't have any earlier questions recorded for this user yet."
    elif _FIRST_QUESTION_PATTERN.search(lowered_query):
        summary = f'The first question you asked was: "{history[0]["query"]}".'
    elif _PREVIOUS_QUESTION_PATTERN.search(lowered_query):
        summary = f'The previous question you asked was: "{history[-1]["query"]}".'
    else:
        recent_questions = [
            f'{index}. "{entry["query"]}"'
            for index, entry in enumerate(reversed(history[-5:]), start=1)
        ]
        summary = f"Your most recent questions were: {'; '.join(recent_questions)}."

    return FinalReport(
        run_id=run_id,
        query=query,
        report_kind=ReportKind.HISTORY_RESPONSE,
        intent=IntentType.MEMORY,
        executive_summary=summary,
        confidence_score=1.0,
    )


def _is_history_request(query: str) -> bool:
    return any(
        pattern.search(query)
        for pattern in (
            _FIRST_QUESTION_PATTERN,
            _PREVIOUS_QUESTION_PATTERN,
            _RECENT_QUESTIONS_PATTERN,
        )
    )


def _looks_business_related(query: str) -> bool:
    lowered_query = query.lower()
    return any(hint in lowered_query for hint in _BUSINESS_HINTS)


def _normalise_query(query: str) -> str:
    return " ".join(query.split())
