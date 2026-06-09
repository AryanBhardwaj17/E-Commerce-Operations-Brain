"""Mock customer support / sentiment data generator."""
from __future__ import annotations

import random
from datetime import date
from typing import Any

from data.mock.sales_projection import get_order_volume_projection
from data.seeds.app_seed_data import get_support_seed

_SUPPORT_SEED = get_support_seed()

SPIKE_DATES: dict[str, dict[str, Any]] = _SUPPORT_SEED["spike_dates"]

COMPLAINT_CATEGORIES = _SUPPORT_SEED["complaint_categories"]

REVIEW_TOPICS = _SUPPORT_SEED["review_topics"]


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xFADE)


def get_complaint_trends(date_str: str) -> dict[str, Any]:
    d = date.fromisoformat(date_str)
    rng = _seed(d)
    spike = SPIKE_DATES.get(date_str)

    base_complaints = 42
    multiplier = spike["complaint_multiplier"] if spike else rng.uniform(0.9, 1.1)
    total = int(base_complaints * multiplier)

    # Distribute across categories
    if spike:
        # Spike category takes the majority
        by_category: dict[str, int] = {spike["primary_category"]: int(total * 0.55)}
        if spike.get("secondary_category"):
            by_category[spike["secondary_category"]] = int(total * 0.25)
        remaining = total - sum(by_category.values())
        other_cats = [c for c in COMPLAINT_CATEGORIES if c not in by_category]
        per_other = max(1, remaining // max(len(other_cats), 1))
        for c in other_cats:
            by_category[c] = per_other
    else:
        by_category = {c: max(1, int(total * rng.uniform(0.05, 0.25))) for c in COMPLAINT_CATEGORIES}

    return {
        "date": date_str,
        "total_complaints": total,
        "vs_baseline_pct": round((multiplier - 1.0) * 100, 1),
        "is_spike": multiplier >= 1.5,
        "by_category": by_category,
        "spike_reason": spike.get("primary_category") if spike else None,
    }


def get_refund_metrics(date_str: str) -> dict[str, Any]:
    rng = _seed(date.fromisoformat(date_str))
    spike = SPIKE_DATES.get(date_str)

    base_refund_rate = 0.032
    refund_rate = (
        base_refund_rate + spike["refund_spike_pct"] * base_refund_rate
        if spike
        else base_refund_rate * rng.uniform(0.9, 1.1)
    )

    orders = get_order_volume_projection(date_str)["total_orders"]
    refunds = int(orders * refund_rate)

    return {
        "date": date_str,
        "refund_requests": refunds,
        "refund_rate_pct": round(refund_rate * 100, 2),
        "vs_baseline_pct": round((refund_rate / base_refund_rate - 1.0) * 100, 1),
        "is_elevated": refund_rate > base_refund_rate * 1.3,
    }


def get_review_sentiment(date_str: str) -> dict[str, Any]:
    d = date.fromisoformat(date_str)
    rng = _seed(d)
    spike = SPIKE_DATES.get(date_str)

    base_positive_pct = 0.72
    if spike:
        positive_pct = base_positive_pct * 0.65  # negative impact from complaints
    else:
        positive_pct = base_positive_pct * rng.uniform(0.95, 1.05)

    total_reviews = rng.randint(80, 140)
    positive = int(total_reviews * positive_pct)
    negative = int(total_reviews * (1 - positive_pct) * 0.6)
    neutral = total_reviews - positive - negative

    topic_sentiment: dict[str, str] = {}
    for topic in REVIEW_TOPICS:
        if spike and topic in ("shipping speed", "customer service"):
            topic_sentiment[topic] = "negative"
        else:
            topic_sentiment[topic] = "positive" if rng.random() > 0.35 else "mixed"

    return {
        "date": date_str,
        "total_reviews": total_reviews,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "positive_pct": round(positive_pct * 100, 1),
        "sentiment_score": round(positive_pct * 5, 2),  # /5 scale
        "topic_sentiment": topic_sentiment,
    }
