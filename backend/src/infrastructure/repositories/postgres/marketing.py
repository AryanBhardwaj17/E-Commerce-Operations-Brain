"""Postgres marketing repository adapter."""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
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
    return random.Random(d.toordinal() ^ 0xCAFE)


class PostgresMarketingRepository:
    def __init__(self, database: PostgresRepositoryDatabase) -> None:
        self.database = database

    def get_campaign_performance(self, date_str: str) -> list[dict[str, Any]]:
        d = date.fromisoformat(date_str)
        rng = _seed(d)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.campaign_id, c.campaign_name, c.channel, c.budget::float8 AS budget,
                       COALESCE(o.is_paused, FALSE) AS is_paused,
                       o.roas_factor::float8 AS roas_factor
                FROM {self.database.qualified('marketing_campaigns')} AS c
                LEFT JOIN {self.database.qualified('marketing_daily_campaign_overrides')} AS o
                  ON o.campaign_id = c.campaign_id AND o.effective_date = %s
                ORDER BY c.campaign_id
                """,
                (d,),
            ).fetchall()

        results = []
        for row in rows:
            campaign_id = str(row["campaign_id"])
            budget = cast(float, row["budget"])
            is_paused = bool(row["is_paused"])
            fallback_roas_factor = rng.uniform(0.85, 1.15)
            roas_factor = float(row["roas_factor"]) if row["roas_factor"] is not None else fallback_roas_factor
            base_roas = 3.2
            roas = 0.0 if is_paused else round(base_roas * roas_factor, 2)
            spend = 0.0 if is_paused else round(budget / 30 * rng.uniform(0.9, 1.1), 2)
            revenue = round(spend * roas, 2)
            results.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": str(row["campaign_name"]),
                    "channel": str(row["channel"]),
                    "status": "paused" if is_paused else "active",
                    "spend": spend,
                    "revenue_attributed": revenue,
                    "roas": roas,
                    "impressions": 0 if is_paused else int(spend * rng.uniform(100, 150)),
                    "clicks": 0 if is_paused else int(spend * rng.uniform(5, 10)),
                    "is_underperforming": (not is_paused) and (roas < 2.0),
                }
            )
        return results

    def get_channel_metrics(self, date_str: str) -> list[dict[str, Any]]:
        performance = self.get_campaign_performance(date_str)
        by_channel: dict[str, dict[str, Any]] = {}
        for item in performance:
            channel = str(item["channel"])
            if channel not in by_channel:
                by_channel[channel] = {"channel": channel, "spend": 0.0, "revenue": 0.0, "campaigns": 0}
            by_channel[channel]["spend"] += item["spend"]
            by_channel[channel]["revenue"] += item["revenue_attributed"]
            by_channel[channel]["campaigns"] += 1

        results = []
        for data in by_channel.values():
            data["roas"] = round(data["revenue"] / data["spend"], 2) if data["spend"] > 0 else 0.0
            results.append(data)
        return sorted(results, key=lambda item: item["roas"])

    def get_active_promotions(self, date_str: str) -> list[dict[str, Any]]:
        effective_date = date.fromisoformat(date_str)
        active_promotions = [item for item in self.get_campaign_performance(date_str) if item["status"] == "active"]

        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT discount_plan_id, product_id, plan_name,
                       discount_pct::float8 AS discount_pct
                FROM {self.database.qualified('inventory_discount_plans')}
                WHERE active = TRUE
                  AND (starts_on IS NULL OR starts_on <= %s)
                  AND (ends_on IS NULL OR ends_on >= %s)
                ORDER BY discount_plan_id
                """,
                (effective_date, effective_date),
            ).fetchall()

        for row in rows:
            active_promotions.append(
                {
                    "campaign_id": str(row["discount_plan_id"]),
                    "campaign_name": str(row["plan_name"]),
                    "channel": "discount_plan",
                    "status": "active",
                    "spend": 0.0,
                    "revenue_attributed": 0.0,
                    "roas": 0.0,
                    "impressions": 0,
                    "clicks": 0,
                    "is_underperforming": False,
                    "product_id": str(row["product_id"]),
                    "discount_pct": float(row["discount_pct"]),
                }
            )
        return active_promotions

    def list_paused_campaigns(self, date_str: str) -> list[dict[str, Any]]:
        return [item for item in self.get_campaign_performance(date_str) if item["status"] == "paused"]

    def pause_campaign(
        self,
        *,
        campaign_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Pause an active campaign by creating a daily override."""
        with self.database.connection() as connection:
            # Check if campaign exists
            campaign_row = connection.execute(
                f"""
                SELECT campaign_id, campaign_name, channel
                FROM {self.database.qualified('marketing_campaigns')}
                WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchone()

            if campaign_row is None:
                return {
                    "status": "error",
                    "message": f"Campaign {campaign_id} not found",
                    "campaign_id": campaign_id,
                }

            # Check if already paused today
            today = datetime.now(UTC).date()
            existing = connection.execute(
                f"""
                SELECT is_paused
                FROM {self.database.qualified('marketing_daily_campaign_overrides')}
                WHERE campaign_id = %s AND effective_date = %s
                """,
                (campaign_id, today),
            ).fetchone()

            if existing and existing["is_paused"]:
                return {
                    "status": "error",
                    "message": f"Campaign {campaign_id} is already paused",
                    "campaign_id": campaign_id,
                }

            # Create or update override to pause
            action_id = f"PAUSE-{uuid4().hex[:8].upper()}"
            connection.execute(
                f"""
                INSERT INTO {self.database.qualified('marketing_daily_campaign_overrides')}
                (campaign_id, effective_date, is_paused, roas_factor, notes)
                VALUES (%s, %s, TRUE, NULL, %s)
                ON CONFLICT (campaign_id, effective_date)
                DO UPDATE SET is_paused = TRUE, notes = EXCLUDED.notes
                """,
                (campaign_id, today, f"{action_id}: {reason}"),
            )
            connection.commit()

            return {
                "status": "success",
                "action": "pause_campaign",
                "campaign_id": campaign_id,
                "campaign_name": campaign_row["campaign_name"],
                "channel": campaign_row["channel"],
                "action_id": action_id,
                "paused_at": datetime.now(UTC).isoformat(),
                "reason": reason,
                "effective_date": today.isoformat(),
                "message": f"Campaign {campaign_id} has been paused",
            }

    def resume_campaign(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Resume a paused campaign by removing or updating daily override."""
        with self.database.connection() as connection:
            # Check if campaign exists
            campaign_row = connection.execute(
                f"""
                SELECT campaign_id, campaign_name, channel
                FROM {self.database.qualified('marketing_campaigns')}
                WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchone()

            if campaign_row is None:
                return {
                    "status": "error",
                    "message": f"Campaign {campaign_id} not found",
                    "campaign_id": campaign_id,
                }

            # Check if campaign is paused today
            today = datetime.now(UTC).date()
            existing = connection.execute(
                f"""
                SELECT is_paused, notes
                FROM {self.database.qualified('marketing_daily_campaign_overrides')}
                WHERE campaign_id = %s AND effective_date = %s
                """,
                (campaign_id, today),
            ).fetchone()

            if not existing or not existing["is_paused"]:
                return {
                    "status": "error",
                    "message": f"Campaign {campaign_id} is not paused",
                    "campaign_id": campaign_id,
                }

            # Update override to resume
            action_id = f"RESUME-{uuid4().hex[:8].upper()}"
            previous_reason = existing.get("notes", "")

            connection.execute(
                f"""
                UPDATE {self.database.qualified('marketing_daily_campaign_overrides')}
                SET is_paused = FALSE, notes = %s
                WHERE campaign_id = %s AND effective_date = %s
                """,
                (f"{action_id}: Resumed", campaign_id, today),
            )
            connection.commit()

            return {
                "status": "success",
                "action": "resume_campaign",
                "campaign_id": campaign_id,
                "campaign_name": campaign_row["campaign_name"],
                "channel": campaign_row["channel"],
                "action_id": action_id,
                "resumed_at": datetime.now(UTC).isoformat(),
                "previous_pause_reason": previous_reason,
                "effective_date": today.isoformat(),
                "message": f"Campaign {campaign_id} has been resumed",
            }

    def get_campaign_status(
        self,
        *,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Get the current status of a campaign."""
        with self.database.connection() as connection:
            campaign_row = connection.execute(
                f"""
                SELECT c.campaign_id, c.campaign_name, c.channel, c.budget::float8 AS budget
                FROM {self.database.qualified('marketing_campaigns')} AS c
                WHERE c.campaign_id = %s
                """,
                (campaign_id,),
            ).fetchone()

            if campaign_row is None:
                return {
                    "status": "error",
                    "message": f"Campaign {campaign_id} not found",
                    "campaign_id": campaign_id,
                }

            # Check override for today
            today = datetime.now(UTC).date()
            override = connection.execute(
                f"""
                SELECT is_paused, roas_factor::float8 AS roas_factor, notes
                FROM {self.database.qualified('marketing_daily_campaign_overrides')}
                WHERE campaign_id = %s AND effective_date = %s
                """,
                (campaign_id, today),
            ).fetchone()

            is_paused = override["is_paused"] if override else False
            current_status = "paused" if is_paused else "active"

            return {
                "campaign_id": campaign_id,
                "campaign_name": campaign_row["campaign_name"],
                "channel": campaign_row["channel"],
                "status": current_status,
                "budget": float(campaign_row["budget"]),
                "override_notes": override["notes"] if override else None,
            }

    # Phase 2: Date range methods
    def get_campaign_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            for campaign in self.get_campaign_performance(date_str):
                result.append({**campaign, "date": date_str, "period": date_str})
        return result

    def get_channel_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        dates = _generate_date_range(start_date, end_date, granularity)
        result: list[dict[str, Any]] = []
        for date_str in dates:
            for channel in self.get_channel_metrics(date_str):
                result.append({**channel, "date": date_str, "period": date_str})
        return result
