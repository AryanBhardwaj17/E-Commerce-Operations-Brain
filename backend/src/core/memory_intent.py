"""Deterministic detection of memory-recall queries.

These are questions where the user wants to recall how similar situations were
handled in the past — they should be answered from the knowledge bases (KEDB/KADB)
rather than triggering a fresh cross-domain diagnostic of the current date.

Examples this matches:
    - "Which actions worked best in past incidents?"
    - "What did we do last time sales dropped like this?"
    - "Has this happened before?"
    - "Did discounts help previously?"

Examples this intentionally does NOT match (handled by other paths):
    - "Fix the issue." / "Restock affected products." (action commands)
    - "Why did sales drop yesterday?" (diagnostic)
    - "Summarize yesterday's business health." (report)
    - "What was my first question?" (conversation history — handled in guardrails)
"""
from __future__ import annotations

import re

# Patterns that indicate the user is asking to recall past incidents, decisions,
# or outcomes. Kept deliberately specific to avoid capturing action commands or
# fresh diagnostics.
_MEMORY_RECALL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat (?:did|have) we (?:do|done|try|tried)\b", re.IGNORECASE),
    re.compile(r"\bwhat was done\b", re.IGNORECASE),
    re.compile(r"\bwhat did we learn\b", re.IGNORECASE),
    re.compile(
        r"\bwhich actions?\b.*\b(?:worked|work|helped|help|were|was)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\b.*\b(?:worked|helped)\b.*\b(?:best|before|previously|last time)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bhas (?:this|it) (?:ever )?happened before\b", re.IGNORECASE),
    re.compile(r"\bhave we (?:seen|had|handled) this\b", re.IGNORECASE),
    re.compile(r"\b(?:last|previous) time\b", re.IGNORECASE),
    re.compile(r"\b(?:in the past|past incidents?|previous incidents?|prior incidents?)\b", re.IGNORECASE),
    re.compile(r"\bdid (?:discounts?|promotions?|restocking|that|this|it)\b.*\b(?:help|work)\b", re.IGNORECASE),
    re.compile(r"\bhistorically\b", re.IGNORECASE),
)


def is_memory_recall_request(query: str) -> bool:
    """Return True if the query is asking to recall past incidents/actions/outcomes."""
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return False
    return any(pattern.search(normalized_query) for pattern in _MEMORY_RECALL_PATTERNS)
