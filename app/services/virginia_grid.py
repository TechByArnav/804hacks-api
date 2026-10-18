from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd


class VirginiaGridService:
    PJM_API_BASE = "https://api.pjm.com/api/v1"
    DOMINION_ZONE = "DOM"
    EIA_API_BASE = "https://api.eia.gov/v2"
    WATTTIME_API_BASE = "https://api.watttime.org/v3"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def initialize(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def _fetch_with_cache(self, key: str, fetcher, ttl: timedelta | None = None) -> Any:
        ttl = ttl or self._cache_ttl
        if key in self._cache:
            data, cached_at = self._cache[key]
            if datetime.now(timezone.utc) - cached_at < ttl:
                return data
        data = await fetcher()
        self._cache[key] = (data, datetime.now(timezone.utc))
        return data

    async def get_current_intensity(self, real_time: bool = True) -> dict | None:
        async def fetch():
            return await self._fetch_pjm_real_time()

        if real_time:
            data = await self._fetch_with_cache("current_intensity", fetch, timedelta(minutes=2))
        else:
            data = await self._fetch_with_cache("current_intensity_fallback", fetch, timedelta(minutes=15))

        if data:
            return self._format_intensity(data, is_real_time=real_time)
        return self._get_fallback_intensity(is_real_time=False)

    async def _fetch_pjm_real_time(self) -> dict | None:
        try:
            if not self._client:
                return None

            url = f"{self.PJM_API_BASE}/emissions/co2/zone/{self.DOMINION_ZONE}/current"
            resp = await self._client.get(url)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def get_historical_intensity(self, hours: int = 24) -> list[dict]:
        async def fetch():
            return await self._fetch_pjm_historical(hours)

        data = await self._fetch_with_cache(f"historical_{hours}h", fetch, timedelta(hours=1))
        if data:
            return [self._format_intensity(d, is_real_time=False) for d in data]
        return self._generate_synthetic_history(hours)

    async def _fetch_pjm_historical(self, hours: int) -> list[dict] | None:
        try:
            if not self._client:
                return None

            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=hours)
            url = f"{self.PJM_API_BASE}/emissions/co2/zone/{self.DOMINION_ZONE}/historical"
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "interval": "5min",
            }
            resp = await self._client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def get_forecast(self, hours: int = 24) -> list[dict]:
        async def fetch():
            return await self._fetch_pjm_forecast(hours)

        data = await self._fetch_with_cache(f"forecast_{hours}h", fetch, timedelta(hours=1))
        if data:
            return [self._format_intensity(d, is_real_time=False) for d in data]
        return self._generate_synthetic_forecast(hours)

    async def _fetch_pjm_forecast(self, hours: int) -> list[dict] | None:
        try:
            if not self._client:
                return None

            url = f"{self.PJM_API_BASE}/emissions/co2/zone/{self.DOMINION_ZONE}/forecast"
            params = {"hours": hours}
            resp = await self._client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def get_generation_mix(self) -> dict[str, float]:
        async def fetch():
            return await self._fetch_eia_generation_mix()

        data = await self._fetch_with_cache("generation_mix", fetch, timedelta(hours=1))
        if data:
            return data
        return self._get_default_generation_mix()

    async def _fetch_eia_generation_mix(self) -> dict[str, float] | None:
        try:
            if not self._client:
                return None

            url = f"{self.EIA_API_BASE}/electricity/rto/region-data/data"
            params = {
                "frequency": "hourly",
                "data[0]": "value",
                "facets[respondent][]": "PJM",
                "facets[type][]": "NG",
                "facets[type][]": "COAL",
                "facets[type][]": "NUC",
                "facets[type][]": "HYD",
                "facets[type][]": "WND",
                "facets[type][]": "SUN",
                "facets[type][]": "OTH",
                "start": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": 0,
                "length": 5000,
            }
            resp = await self._client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_eia_generation_mix(data)
        except Exception:
            pass
        return None

    def _parse_eia_generation_mix(self, data: dict) -> dict[str, float]:
        totals = {}
        for item in data.get("response", {}).get("data", []):
            fuel = item.get("fueltype", "OTH")
            value = item.get("value", 0)
            totals[fuel] = totals.get(fuel, 0) + value

        total = sum(totals.values())
        if total == 0:
            return self._get_default_generation_mix()

        return {k: round(v / total * 100, 1) for k, v in totals.items()}

    def _get_default_generation_mix(self) -> dict[str, float]:
        return {
            "natural_gas": 42.0,
            "nuclear": 33.0,
            "coal": 12.0,
            "solar": 6.0,
            "wind": 3.0,
            "hydro": 2.0,
            "other": 2.0,
        }

    def _format_intensity(self, data: dict, is_real_time: bool) -> dict:
        intensity_lb_mwh = data.get("co2_lb_per_mwh", data.get("value", 800))
        intensity_g_kwh = intensity_lb_mwh * 0.453592

        return {
            "timestamp": datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "carbon_intensity_lb_per_mwh": round(intensity_lb_mwh, 1),
            "carbon_intensity_g_per_kwh": round(intensity_g_kwh, 1),
            "region": "VA-DOM",
            "source": data.get("source", "PJM"),
            "is_real_time": is_real_time,
        }

    def _get_fallback_intensity(self, is_real_time: bool) -> dict:
        base = 800
        variance = random.uniform(-100, 100)
        intensity_lb_mwh = max(200, base + variance)
        intensity_g_kwh = intensity_lb_mwh * 0.453592

        return {
            "timestamp": datetime.now(timezone.utc),
            "carbon_intensity_lb_per_mwh": round(intensity_lb_mwh, 1),
            "carbon_intensity_g_per_kwh": round(intensity_g_kwh, 1),
            "region": "VA-DOM",
            "source": "fallback_estimate",
            "is_real_time": is_real_time,
        }

    def _generate_synthetic_history(self, hours: int) -> list[dict]:
        now = datetime.now(timezone.utc)
        base = 800
        history = []

        for i in range(hours * 12):
            timestamp = now - timedelta(minutes=5 * (hours * 12 - i))
            hour = timestamp.hour
            daily_cycle = 100 * (0.5 + 0.5 * abs((hour - 12) / 12))
            noise = random.uniform(-50, 50)
            intensity_lb_mwh = base + daily_cycle + noise
            intensity_lb_mwh = max(200, intensity_lb_mwh)
            intensity_g_kwh = intensity_lb_mwh * 0.453592

            history.append({
                "timestamp": timestamp,
                "carbon_intensity_lb_per_mwh": round(intensity_lb_mwh, 1),
                "carbon_intensity_g_per_kwh": round(intensity_g_kwh, 1),
                "region": "VA-DOM",
                "source": "synthetic",
                "is_real_time": False,
            })

        return history

    def _generate_synthetic_forecast(self, hours: int) -> list[dict]:
        now = datetime.now(timezone.utc)
        base = 800
        forecast = []

        for i in range(hours * 12):
            timestamp = now + timedelta(minutes=5 * (i + 1))
            hour = timestamp.hour
            daily_cycle = 100 * (0.5 + 0.5 * abs((hour - 12) / 12))
            noise = random.uniform(-30, 30)
            intensity_lb_mwh = base + daily_cycle + noise
            intensity_lb_mwh = max(200, intensity_lb_mwh)
            intensity_g_kwh = intensity_lb_mwh * 0.453592

            forecast.append({
                "timestamp": timestamp,
                "carbon_intensity_lb_per_mwh": round(intensity_lb_mwh, 1),
                "carbon_intensity_g_per_kwh": round(intensity_g_kwh, 1),
                "region": "VA-DOM",
                "source": "forecast_model",
                "is_real_time": False,
            })

        return forecast

    async def get_hourly_intensity(self) -> dict[str, Any]:
        """Return 24 hourly carbon intensity points from 1 AM through 12 AM,
        plus summary stats for carbon-aware scheduling."""
        async def fetch():
            return await self._fetch_pjm_hourly()

        data = await self._fetch_with_cache("hourly_intensity", fetch, timedelta(minutes=15))
        if data:
            return data
        return self._generate_synthetic_hourly()

    async def _fetch_pjm_hourly(self) -> dict[str, Any] | None:
        try:
            if not self._client:
                return None

            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1) - timedelta(minutes=1)
            url = f"{self.PJM_API_BASE}/emissions/co2/zone/{self.DOMINION_ZONE}/historical"
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "interval": "60min",
            }
            resp = await self._client.get(url, params=params)
            if resp.status_code == 200:
                raw = resp.json()
                return self._build_hourly_response(raw)
        except Exception:
            pass
        return None

    def _build_hourly_response(self, raw: list[dict]) -> dict[str, Any]:
        hours: dict[int, dict] = {}
        for item in raw:
            ts = datetime.fromisoformat(item.get("timestamp", datetime.now(timezone.utc).isoformat()))
            hour = ts.hour
            g_kwh = item.get("co2_lb_per_mwh", item.get("value", 800)) * 0.453592
            hours[hour] = {
                "hour": hour,
                "label": self._hour_label(hour),
                "carbon_intensity_g_per_kwh": round(g_kwh, 1),
                "carbon_intensity_lb_per_mwh": round(g_kwh / 0.453592, 1),
            }

        ordered = [hours.get(h, self._empty_hour(h)) for h in range(1, 25)]
        return self._compute_summary(ordered)

    def _generate_synthetic_hourly(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        base = 700
        hours_data = []

        for h in range(1, 25):
            ts = now.replace(hour=h % 24, minute=0, second=0, microsecond=0)
            # Daily cycle: lower at night (2-5 AM), higher mid-day, peak ~6 PM
            if h in (1, 2, 3, 4, 5):
                cycle = -80  # night dip
            elif h in (6, 7, 8):
                cycle = -20  # morning ramp
            elif h in (9, 10, 11, 12, 13, 14, 15, 16, 17):
                cycle = 40   # day plateau
            elif h in (18, 19, 20, 21):
                cycle = 90   # evening peak
            else:
                cycle = 10   # late night taper

            noise = random.uniform(-15, 15)
            g_kwh = base + cycle + noise
            g_kwh = max(150, g_kwh)

            hours_data.append({
                "hour": h,
                "label": self._hour_label(h),
                "carbon_intensity_g_per_kwh": round(g_kwh, 1),
                "carbon_intensity_lb_per_mwh": round(g_kwh / 0.453592, 1),
                "timestamp": ts.isoformat(),
            })

        return self._compute_summary(hours_data)

    def _compute_summary(self, hours: list[dict]) -> dict[str, Any]:
        values = [h["carbon_intensity_g_per_kwh"] for h in hours]
        current_hour = datetime.now(timezone.utc).hour
        current = next((h for h in hours if h["hour"] == current_hour), hours[0])

        # Best 6-hour window
        best_start = 1
        best_avg = float("inf")
        for start in range(1, 19):  # 1 AM through 6 PM start (6-hour window fits in 24h)
            window = values[start - 1:start + 5]
            avg = sum(window) / len(window)
            if avg < best_avg:
                best_avg = avg
                best_start = start

        best_end = best_start + 5
        if best_end > 24:
            best_end = best_end - 24

        dirtiest_idx = values.index(max(values))
        dirtiest_hour = hours[dirtiest_idx]["hour"]
        dirtiest_val = values[dirtiest_idx]

        savings_pct = ((current["carbon_intensity_g_per_kwh"] - best_avg) / current["carbon_intensity_g_per_kwh"] * 100) if current["carbon_intensity_g_per_kwh"] else 0

        return {
            "region": "VA-DOM",
            "current_hour": current,
            "hours": hours,
            "summary": {
                "now_g_per_kwh": round(current["carbon_intensity_g_per_kwh"], 1),
                "best_window_start": best_start,
                "best_window_end": best_end,
                "best_window_avg_g_per_kwh": round(best_avg, 1),
                "cleaner_by_percent": round(max(0, savings_pct), 1),
                "dirtiest_hour": dirtiest_hour,
                "dirtiest_hour_g_per_kwh": round(dirtiest_val, 1),
                "data_points": len(hours),
            },
        }

    def _hour_label(self, hour: int) -> str:
        if hour == 0:
            return "12 AM"
        if hour < 12:
            return f"{hour} AM"
        if hour == 12:
            return "12 PM"
        return f"{hour - 12} PM"

    def _empty_hour(self, hour: int) -> dict:
        return {
            "hour": hour,
            "label": self._hour_label(hour),
            "carbon_intensity_g_per_kwh": 0.0,
            "carbon_intensity_lb_per_mwh": 0.0,
            "timestamp": "",
        }