"""Mock marketing / campaign data generator."""
from __future__ import annotations

import random
from datetime import date
from typing import Any, cast

from data.mock.promotion_views import list_active_discount_promotions
from data.seeds.app_seed_data import get_marketing_seed

_MARKETING_SEED = get_marketing_seed()

CAMPAIGNS = _MARKETING_SEED["campaigns"]

CHANNELS = _MARKETING_SEED["channels"]

PAUSED_DATES: dict[str, list[str]] = _MARKETING_SEED["paused_dates"]

UNDERPERFORM_DATES: dict[str, dict[str, float]] = _MARKETING_SEED["underperform_dates"]


def _seed(d: date) -> random.Random:
    return random.Random(d.toordinal() ^ 0xCAFE)


def get_campaign_performance(date_str: str) -> list[dict[str, Any]]:
    d = date.fromisoformat(date_str)
    rng = _seed(d)
    paused = set(PAUSED_DATES.get(date_str, []))
    underperform = UNDERPERFORM_DATES.get(date_str, {})

    results = []
    for camp in CAMPAIGNS:
        campaign_id = str(camp["id"])
        budget = cast(float, camp["budget"])
        is_paused = campaign_id in paused
        roas_factor = underperform.get(campaign_id, rng.uniform(0.85, 1.15))
        base_roas = 3.2
        roas = 0.0 if is_paused else round(base_roas * roas_factor, 2)
        spend = 0.0 if is_paused else round(budget / 30 * rng.uniform(0.9, 1.1), 2)
        revenue = round(spend * roas, 2)
        results.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": str(camp["name"]),
                "channel": str(camp["channel"]),
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


def get_channel_metrics(date_str: str) -> list[dict[str, Any]]:
    perf = get_campaign_performance(date_str)
    by_channel: dict[str, dict[str, Any]] = {}
    for p in perf:
        ch = p["channel"]
        if ch not in by_channel:
            by_channel[ch] = {"channel": ch, "spend": 0.0, "revenue": 0.0, "campaigns": 0}
        by_channel[ch]["spend"] += p["spend"]
        by_channel[ch]["revenue"] += p["revenue_attributed"]
        by_channel[ch]["campaigns"] += 1

    results = []
    for _channel, data in by_channel.items():
        data["roas"] = round(data["revenue"] / data["spend"], 2) if data["spend"] > 0 else 0.0
        results.append(data)
    return sorted(results, key=lambda x: x["roas"])  # worst performing first


def get_active_promotions(date_str: str) -> list[dict[str, Any]]:
    perf = get_campaign_performance(date_str)
    active_promotions = [p for p in perf if p["status"] == "active"]
    active_promotions.extend(list_active_discount_promotions(date_str))
    return active_promotions


def list_paused_campaigns(date_str: str) -> list[dict[str, Any]]:
    perf = get_campaign_performance(date_str)
    return [p for p in perf if p["status"] == "paused"]
