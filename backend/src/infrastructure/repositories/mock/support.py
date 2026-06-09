"""Mock support repository adapter."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from data.mock import support as support_data


class MockSupportRepository:
    """Mock implementation of SupportRepository with in-memory ticket tracking."""

    def __init__(self) -> None:
        # In-memory store for support tickets
        self._tickets: dict[str, dict[str, Any]] = {}
    def get_complaint_trends(self, date_str: str) -> dict[str, Any]:
        return support_data.get_complaint_trends(date_str)

    def get_refund_metrics(self, date_str: str) -> dict[str, Any]:
        return support_data.get_refund_metrics(date_str)

    def get_review_sentiment(self, date_str: str) -> dict[str, Any]:
        return support_data.get_review_sentiment(date_str)

    def create_support_ticket(
        self,
        *,
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "general",
        assigned_to: str | None = None,
    ) -> dict[str, Any]:
        """Create a new support ticket."""
        ticket_id = f"TICKET-{uuid4().hex[:8].upper()}"
        created_at = datetime.now(UTC).isoformat()

        ticket = {
            "ticket_id": ticket_id,
            "title": title,
            "description": description,
            "priority": priority.lower(),
            "category": category,
            "status": "open",
            "assigned_to": assigned_to or "unassigned",
            "created_at": created_at,
            "updated_at": created_at,
            "created_by": "system",
        }

        # Store in memory
        self._tickets[ticket_id] = ticket

        return {
            "status": "success",
            "action": "create_support_ticket",
            "ticket": ticket,
            "message": f"Support ticket {ticket_id} created successfully",
        }

    def get_ticket_status(
        self,
        *,
        ticket_id: str,
    ) -> dict[str, Any]:
        """Get the status of a support ticket."""
        ticket = self._tickets.get(ticket_id)

        if ticket is None:
            return {
                "status": "error",
                "message": f"Ticket {ticket_id} not found",
                "ticket_id": ticket_id,
            }

        return {
            "status": "success",
            "ticket": ticket,
        }

    # Phase 2: Date range methods
    def get_complaint_trends_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return complaint trends time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        return [
            {
                "date": date_str,
                "period": date_str,
                **support_data.get_complaint_trends(date_str)
            }
            for date_str in dates
        ]

    def get_refund_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return refund metrics time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        return [
            {
                "date": date_str,
                "period": date_str,
                **support_data.get_refund_metrics(date_str)
            }
            for date_str in dates
        ]

    def _generate_date_range(
        self, start_date: str, end_date: str, granularity: str
    ) -> list[str]:
        """Generate list of dates between start and end with given granularity."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        dates = []
        current = start

        if granularity == "weekly":
            delta = timedelta(days=7)
        elif granularity == "monthly":
            delta = timedelta(days=30)
        else:  # daily
            delta = timedelta(days=1)

        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += delta

        return dates