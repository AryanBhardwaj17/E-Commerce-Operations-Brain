"""Mock sales repository adapter."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from data.mock import sales as sales_data


class MockSalesRepository:
    def get_revenue_metrics(self, date_str: str) -> dict[str, Any]:
        return sales_data.get_revenue_metrics(date_str)

    def get_order_volume(self, date_str: str) -> dict[str, Any]:
        return sales_data.get_order_volume(date_str)

    def get_regional_sales(self, date_str: str) -> list[dict[str, Any]]:
        return sales_data.get_regional_sales(date_str)

    def get_product_performance(self, date_str: str) -> list[dict[str, Any]]:
        return sales_data.get_product_performance(date_str)

    def detect_sales_anomaly(self, date_str: str) -> dict[str, Any]:
        return sales_data.detect_sales_anomaly(date_str)

    # Phase 2: Date range methods
    def get_revenue_metrics_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return revenue metrics time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        return [
            {
                "date": date_str,
                "period": date_str,
                **sales_data.get_revenue_metrics(date_str)
            }
            for date_str in dates
        ]

    def get_order_volume_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return order volume time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        return [
            {
                "date": date_str,
                "period": date_str,
                **sales_data.get_order_volume(date_str)
            }
            for date_str in dates
        ]

    def get_regional_sales_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return regional sales time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            regional_data = sales_data.get_regional_sales(date_str)
            for region in regional_data:
                result.append({**region, "date": date_str, "period": date_str})
        return result

    def get_product_performance_range(
        self, start_date: str, end_date: str, granularity: str = "daily"
    ) -> list[dict[str, Any]]:
        """Return product performance time series."""
        dates = self._generate_date_range(start_date, end_date, granularity)
        result = []
        for date_str in dates:
            products = sales_data.get_product_performance(date_str)
            for product in products:
                result.append({**product, "date": date_str, "period": date_str})
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
            # Simplified: use 30-day months
            delta = timedelta(days=30)
        else:  # daily
            delta = timedelta(days=1)

        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += delta

        return dates