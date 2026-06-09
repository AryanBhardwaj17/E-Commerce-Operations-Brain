"""Postgres support repository adapter."""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase


def _generate_date_range(start_date: str, end_date: str, granularity: str) -> list[str]:
    """Generate list of dates between start and end with given granularity."""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    if granularity == "weekly":
        delta = timedelta(days=7)
    elif granularity == "monthly":
        delta = timedelta(days=30)
    else:  # daily
        delta = timedelta(days=1)

    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += delta
    return dates


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xFADE)


def _sales_seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xDEAD)


def _calculate_total_orders(date_str: str, order_drop_pct: float | None) -> int:
    d = date.fromisoformat(date_str)
    rng = _sales_seed(d)
    base_orders = 820
    seasonal = 0.70 if d.weekday() >= 5 else 1.0
    orders = int(base_orders * seasonal * rng.uniform(0.93, 1.07))
    if order_drop_pct is not None:
        orders = int(orders * (1.0 - order_drop_pct))
    return orders


class PostgresSupportRepository:
    def __init__(self, database: PostgresRepositoryDatabase) -> None:
        self.database = database

    def _get_spike(self, date_str: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT effective_date, complaint_multiplier::float8 AS complaint_multiplier,
                       refund_spike_pct::float8 AS refund_spike_pct,
                       primary_category, secondary_category
                FROM {self.database.qualified('support_daily_spikes')}
                WHERE effective_date = %s
                """,
                (date.fromisoformat(date_str),),
            ).fetchone()
        if row is None:
            return None
        return {
            "effective_date": row["effective_date"].isoformat(),
            "complaint_multiplier": float(row["complaint_multiplier"]),
            "refund_spike_pct": float(row["refund_spike_pct"]),
            "primary_category": str(row["primary_category"]),
            "secondary_category": str(row["secondary_category"]) if row["secondary_category"] else None,
        }

    def _get_complaint_categories(self) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT category FROM {self.database.qualified('support_complaint_categories')} ORDER BY sort_order, category"
            ).fetchall()
        return [str(row["category"]) for row in rows]

    def _get_review_topics(self) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT topic FROM {self.database.qualified('support_review_topics')} ORDER BY sort_order, topic"
            ).fetchall()
        return [str(row["topic"]) for row in rows]

    def _get_sales_anomaly_order_drop_pct(self, date_str: str) -> float | None:
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT order_drop_pct::float8 AS order_drop_pct FROM {self.database.qualified('sales_daily_anomalies')} WHERE effective_date = %s",
                (date.fromisoformat(date_str),),
            ).fetchone()
        if row is None:
            return None
        return float(row["order_drop_pct"])

    def get_complaint_trends(self, date_str: str) -> dict[str, Any]:
        d = date.fromisoformat(date_str)
        rng = _seed(d)
        spike = self._get_spike(date_str)

        base_complaints = 42
        multiplier = float(spike["complaint_multiplier"]) if spike else rng.uniform(0.9, 1.1)
        total = int(base_complaints * multiplier)

        if spike:
            by_category: dict[str, int] = {str(spike["primary_category"]): int(total * 0.55)}
            if spike.get("secondary_category"):
                by_category[str(spike["secondary_category"])] = int(total * 0.25)
            remaining = total - sum(by_category.values())
            other_categories = [category for category in self._get_complaint_categories() if category not in by_category]
            per_other = max(1, remaining // max(len(other_categories), 1))
            for category in other_categories:
                by_category[category] = per_other
        else:
            by_category = {
                category: max(1, int(total * rng.uniform(0.05, 0.25)))
                for category in self._get_complaint_categories()
            }

        return {
            "date": date_str,
            "total_complaints": total,
            "vs_baseline_pct": round((multiplier - 1.0) * 100, 1),
            "is_spike": multiplier >= 1.5,
            "by_category": by_category,
            "spike_reason": spike.get("primary_category") if spike else None,
        }

    def get_refund_metrics(self, date_str: str) -> dict[str, Any]:
        rng = _seed(date.fromisoformat(date_str))
        spike = self._get_spike(date_str)

        base_refund_rate = 0.032
        refund_rate = (
            base_refund_rate + float(spike["refund_spike_pct"]) * base_refund_rate
            if spike
            else base_refund_rate * rng.uniform(0.9, 1.1)
        )

        orders = _calculate_total_orders(date_str, self._get_sales_anomaly_order_drop_pct(date_str))
        refunds = int(orders * refund_rate)

        return {
            "date": date_str,
            "refund_requests": refunds,
            "refund_rate_pct": round(refund_rate * 100, 2),
            "vs_baseline_pct": round((refund_rate / base_refund_rate - 1.0) * 100, 1),
            "is_elevated": refund_rate > base_refund_rate * 1.3,
        }

    def get_review_sentiment(self, date_str: str) -> dict[str, Any]:
        d = date.fromisoformat(date_str)
        rng = _seed(d)
        spike = self._get_spike(date_str)

        base_positive_pct = 0.72
        if spike:
            positive_pct = base_positive_pct * 0.65
        else:
            positive_pct = base_positive_pct * rng.uniform(0.95, 1.05)

        total_reviews = rng.randint(80, 140)
        positive = int(total_reviews * positive_pct)
        negative = int(total_reviews * (1 - positive_pct) * 0.6)
        neutral = total_reviews - positive - negative

        topic_sentiment: dict[str, str] = {}
        for topic in self._get_review_topics():
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
            "sentiment_score": round(positive_pct * 5, 2),
            "topic_sentiment": topic_sentiment,
        }

    # Phase 2: Date range methods
    def get_complaint_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        return [
            {"date": date_str, "period": date_str, **self.get_complaint_trends(date_str)}
            for date_str in dates
        ]

    def get_refund_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        return [
            {"date": date_str, "period": date_str, **self.get_refund_metrics(date_str)}
            for date_str in dates
        ]

    def create_support_ticket(
        self,
        *,
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "general",
        assigned_to: str | None = None,
    ) -> dict[str, Any]:
        """Create a new support ticket in the database."""
        ticket_id = f"TICKET-{uuid4().hex[:8].upper()}"
        created_at = datetime.now(UTC)

        with self.database.connection() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.database.qualified('support_tickets')}
                (ticket_id, title, description, priority, category, status, assigned_to, created_at, updated_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ticket_id,
                    title,
                    description,
                    priority.lower(),
                    category,
                    "open",
                    assigned_to or "unassigned",
                    created_at,
                    created_at,
                    "system",
                ),
            )
            connection.commit()

        return {
            "status": "success",
            "action": "create_support_ticket",
            "ticket": {
                "ticket_id": ticket_id,
                "title": title,
                "description": description,
                "priority": priority.lower(),
                "category": category,
                "status": "open",
                "assigned_to": assigned_to or "unassigned",
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "created_by": "system",
            },
            "message": f"Support ticket {ticket_id} created successfully",
        }

    def get_ticket_status(
        self,
        *,
        ticket_id: str,
    ) -> dict[str, Any]:
        """Get the status of a support ticket."""
        with self.database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT ticket_id, title, description, priority, category, status,
                       assigned_to, created_at, updated_at, created_by
                FROM {self.database.qualified('support_tickets')}
                WHERE ticket_id = %s
                """,
                (ticket_id,),
            ).fetchone()

        if row is None:
            return {
                "status": "error",
                "message": f"Ticket {ticket_id} not found",
                "ticket_id": ticket_id,
            }

        return {
            "status": "success",
            "ticket": {
                "ticket_id": row["ticket_id"],
                "title": row["title"],
                "description": row["description"],
                "priority": row["priority"],
                "category": row["category"],
                "status": row["status"],
                "assigned_to": row["assigned_to"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                "created_by": row["created_by"],
            },
        }
