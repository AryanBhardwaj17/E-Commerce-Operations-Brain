"""Mock marketing repository adapter."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from data.mock import marketing as marketing_data


class MockMarketingRepository:
    """Mock implementation of MarketingRepository with in-memory campaign state."""

    def __init__(self) -> None:
        # In-memory store for campaign status changes
        self._campaign_state: dict[str, dict[str, Any]] = {}
    def get_campaign_performance(self, date_str: str) -> list[dict[str, Any]]:
        return marketing_data.get_campaign_performance(date_str)

    def get_channel_metrics(self, date_str: str) -> list[dict[str, Any]]:
        return marketing_data.get_channel_metrics(date_str)

    def get_active_promotions(self, date_str: str) -> list[dict[str, Any]]:
        return marketing_data.get_active_promotions(date_str)

    def list_paused_campaigns(self, date_str: str) -> list[dict[str, Any]]:
        return marketing_data.list_paused_campaigns(date_str)

    def pause_campaign(
        self,
        *,
        campaign_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Pause an active campaign."""
        # Get current campaign status
        campaigns = marketing_data.get_campaign_performance(
            datetime.now(UTC).strftime("%Y-%m-%d")
        )
        campaign = next((c for c in campaigns if c["campaign_id"] == campaign_id), None)

        if campaign is None:
            return {
                "status": "error",
                "message": f"Campaign {campaign_id} not found",
                "campaign_id": campaign_id,
            }

        # Check if already paused
        current_status = self._campaign_state.get(campaign_id, {}).get("status")
        if current_status == "paused" or campaign.get("status") == "paused":
            return {
                "status": "error",
                "message": f"Campaign {campaign_id} is already paused",
                "campaign_id": campaign_id,
            }

        # Store the paused state
        action_id = f"PAUSE-{uuid4().hex[:8].upper()}"
        self._campaign_state[campaign_id] = {
            "status": "paused",
            "paused_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "action_id": action_id,
            "previous_status": campaign.get("status", "active"),
        }

        return {
            "status": "success",
            "action": "pause_campaign",
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("campaign_name", ""),
            "action_id": action_id,
            "paused_at": self._campaign_state[campaign_id]["paused_at"],
            "reason": reason,
            "previous_status": campaign.get("status", "active"),
            "message": f"Campaign {campaign_id} has been paused",
        }

    def resume_campaign(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Resume a paused campaign."""
        # Get current campaign status
        campaigns = marketing_data.get_campaign_performance(
            datetime.now(UTC).strftime("%Y-%m-%d")
        )
        campaign = next((c for c in campaigns if c["campaign_id"] == campaign_id), None)

        if campaign is None:
            return {
                "status": "error",
                "message": f"Campaign {campaign_id} not found",
                "campaign_id": campaign_id,
            }

        # Check if campaign is paused
        current_state = self._campaign_state.get(campaign_id, {})
        is_paused = current_state.get("status") == "paused" or campaign.get(
            "status"
        ) == "paused"

        if not is_paused:
            return {
                "status": "error",
                "message": f"Campaign {campaign_id} is not paused",
                "campaign_id": campaign_id,
            }

        # Resume the campaign
        action_id = f"RESUME-{uuid4().hex[:8].upper()}"
        previous_state = self._campaign_state.get(campaign_id, {})
        self._campaign_state[campaign_id] = {
            "status": "active",
            "resumed_at": datetime.now(UTC).isoformat(),
            "action_id": action_id,
            "previous_pause_reason": previous_state.get("reason", ""),
        }

        return {
            "status": "success",
            "action": "resume_campaign",
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("campaign_name", ""),
            "action_id": action_id,
            "resumed_at": self._campaign_state[campaign_id]["resumed_at"],
            "previous_pause_reason": previous_state.get("reason", ""),
            "message": f"Campaign {campaign_id} has been resumed",
        }

    def get_campaign_status(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Get the current status of a campaign."""
        campaigns = marketing_data.get_campaign_performance(
            datetime.now(UTC).strftime("%Y-%m-%d")
        )
        campaign = next((c for c in campaigns if c["campaign_id"] == campaign_id), None)

        if campaign is None:
            return {
                "status": "error",
                "message": f"Campaign {campaign_id} not found",
                "campaign_id": campaign_id,
            }

        # Merge with any state changes we've stored
        state = self._campaign_state.get(campaign_id, {})
        current_status = state.get("status", campaign.get("status", "active"))

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("campaign_name", ""),
            "status": current_status,
            "channel": campaign.get("channel", ""),
            "spend": campaign.get("spend", 0),
            "roas": campaign.get("roas", 0),
            "state_changes": state,
        }

    # Phase 2: Date range methods
    def get_campaign_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return campaign performance time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            campaigns = marketing_data.get_campaign_performance(date_str)
            for campaign in campaigns:
                result.append({**campaign, "date": date_str, "period": date_str})
        return result

    def get_channel_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return channel metrics time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            channels = marketing_data.get_channel_metrics(date_str)
            for channel in channels:
                result.append({**channel, "date": date_str, "period": date_str})
        return result

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