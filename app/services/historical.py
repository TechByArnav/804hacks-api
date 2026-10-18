from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


class HistoricalCarbonService:
    def __init__(self):
        self._historical_data: list[dict] | None = None
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await self._load_historical_data()
        self._initialized = True

    async def _load_historical_data(self):
        self._historical_data = self._generate_synthetic_historical_data(days=365)

    def _generate_synthetic_historical_data(self, days: int) -> list[dict]:
        now = datetime.now(timezone.utc)
        data = []

        for day in range(days):
            date = now - timedelta(days=day)
            seasonal_factor = 1 + 0.15 * math.sin(2 * math.pi * (date.timetuple().tm_yday - 80) / 365)
            base_intensity = 380 * seasonal_factor

            for hour in range(24):
                hour_factor = 1 + 0.1 * abs((hour - 14) / 12)
                noise = random.uniform(-20, 20)
                intensity = base_intensity * hour_factor + noise
                intensity = max(150, intensity)

                timestamp = date.replace(hour=hour, minute=random.randint(0, 59))
                data.append({
                    "timestamp": timestamp,
                    "carbon_intensity_g_per_kwh": round(intensity, 1),
                })

        data.sort(key=lambda x: x["timestamp"])
        return data

    async def compare(
        self,
        current_intensity_g_per_kwh: float,
        days: int = 30,
    ) -> dict[str, Any]:
        if not self._historical_data:
            await self._load_historical_data()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            d for d in self._historical_data
            if d["timestamp"] >= cutoff
        ]

        if not recent:
            return self._empty_comparison(current_intensity_g_per_kwh, days)

        values = [d["carbon_intensity_g_per_kwh"] for d in recent]
        historical_avg = sum(values) / len(values)
        historical_min = min(values)
        historical_max = max(values)

        below_count = sum(1 for v in values if v < current_intensity_g_per_kwh)
        percentile = (below_count / len(values)) * 100

        return {
            "current_intensity_g_per_kwh": round(current_intensity_g_per_kwh, 1),
            "historical_avg_g_per_kwh": round(historical_avg, 1),
            "historical_min_g_per_kwh": round(historical_min, 1),
            "historical_max_g_per_kwh": round(historical_max, 1),
            "percentile": round(percentile, 1),
            "period": f"last_{days}_days",
            "data_points": len(values),
        }

    def _empty_comparison(self, current: float, days: int) -> dict[str, Any]:
        return {
            "current_intensity_g_per_kwh": round(current, 1),
            "historical_avg_g_per_kwh": round(current, 1),
            "historical_min_g_per_kwh": round(current, 1),
            "historical_max_g_per_kwh": round(current, 1),
            "percentile": 50.0,
            "period": f"last_{days}_days",
            "data_points": 0,
        }

    async def get_time_series(self, days: int = 30) -> list[dict]:
        if not self._historical_data:
            await self._load_historical_data()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            d for d in self._historical_data
            if d["timestamp"] >= cutoff
        ]

        return [
            {
                "timestamp": d["timestamp"].isoformat(),
                "carbon_intensity_g_per_kwh": d["carbon_intensity_g_per_kwh"],
            }
            for d in recent
        ]

    async def get_daily_averages(self, days: int = 30) -> list[dict]:
        if not self._historical_data:
            await self._load_historical_data()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            d for d in self._historical_data
            if d["timestamp"] >= cutoff
        ]

        daily: dict[str, list[float]] = {}
        for d in recent:
            day_key = d["timestamp"].date().isoformat()
            if day_key not in daily:
                daily[day_key] = []
            daily[day_key].append(d["carbon_intensity_g_per_kwh"])

        return [
            {
                "date": day,
                "avg_intensity_g_per_kwh": round(sum(vals) / len(vals), 1),
                "min_intensity_g_per_kwh": round(min(vals), 1),
                "max_intensity_g_per_kwh": round(max(vals), 1),
            }
            for day, vals in sorted(daily.items())
        ]

    async def get_percentile_rank(self, intensity: float, days: int = 365) -> float:
        if not self._historical_data:
            await self._load_historical_data()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            d for d in self._historical_data
            if d["timestamp"] >= cutoff
        ]

        if not recent:
            return 50.0

        values = [d["carbon_intensity_g_per_kwh"] for d in recent]
        below = sum(1 for v in values if v < intensity)
        return round((below / len(values)) * 100, 1)

    async def close(self):
        pass


import math