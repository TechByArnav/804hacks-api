from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.services.virginia_grid import VirginiaGridService
from app.services.code_energy import CodeEnergyEstimator
from app.services.historical import HistoricalCarbonService


virginia_grid = VirginiaGridService()
code_estimator = CodeEnergyEstimator()
historical = HistoricalCarbonService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await virginia_grid.initialize()
    await historical.initialize()
    yield
    await virginia_grid.close()
    await historical.close()


app = FastAPI(
    title="CarbonSense — Virginia Grid Carbon API",
    description="Real-time Virginia grid carbon intensity + code energy/emissions estimation",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount landing page at /landing
landing_dir = os.path.join(os.path.dirname(__file__), "..", "landing")
if os.path.isdir(landing_dir):
    app.mount("/landing", StaticFiles(directory=landing_dir, html=True), name="landing")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/landing/index.html")


@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/landing/docs.html")


@app.get("/contact", include_in_schema=False)
async def contact_redirect():
    return RedirectResponse(url="/landing/contact.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "carbonsense-api"}


class CarbonIntensityResponse(BaseModel):
    timestamp: datetime
    carbon_intensity_lb_per_mwh: float
    carbon_intensity_g_per_kwh: float
    region: str = "VA-DOM"
    source: str
    is_real_time: bool


class CodeAnalysisRequest(BaseModel):
    code: str = Field(..., description="Source code to analyze")
    language: str = Field(default="python", description="Programming language")
    runtime_seconds: float | None = Field(default=None, description="Actual runtime if known")
    cpu_utilization: float = Field(default=0.5, ge=0.0, le=1.0, description="Average CPU utilization (0-1)")
    memory_mb: float = Field(default=256, ge=0, description="Memory usage in MB")


class CodeEnergyResponse(BaseModel):
    estimated_energy_kwh: float
    estimated_emissions_g_co2: float
    estimated_emissions_lb_co2: float
    carbon_intensity_used_g_per_kwh: float
    breakdown: dict[str, Any]
    timestamp: datetime
    region: str = "VA-DOM"


class HistoricalComparisonResponse(BaseModel):
    current_intensity_g_per_kwh: float
    historical_avg_g_per_kwh: float
    historical_min_g_per_kwh: float
    historical_max_g_per_kwh: float
    percentile: float
    period: str
    data_points: int


class GridStatusResponse(BaseModel):
    region: str
    current_intensity: CarbonIntensityResponse
    forecast: list[CarbonIntensityResponse]
    generation_mix: dict[str, float]


@app.get("/api/v1/carbon/intensity", response_model=CarbonIntensityResponse)
async def get_current_intensity(
    real_time: bool = Query(default=True, description="Use real-time data if available"),
) -> CarbonIntensityResponse:
    intensity = await virginia_grid.get_current_intensity(real_time=real_time)
    if intensity is None:
        raise HTTPException(status_code=503, detail="Unable to fetch carbon intensity data")
    return intensity


@app.get("/api/v1/carbon/intensity/history", response_model=list[CarbonIntensityResponse])
async def get_historical_intensity(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to retrieve"),
) -> list[CarbonIntensityResponse]:
    return await virginia_grid.get_historical_intensity(hours=hours)


@app.get("/api/v1/carbon/forecast", response_model=list[CarbonIntensityResponse])
async def get_forecast(
    hours: int = Query(default=24, ge=1, le=72, description="Hours of forecast to retrieve"),
) -> list[CarbonIntensityResponse]:
    return await virginia_grid.get_forecast(hours=hours)


@app.get("/api/v1/carbon/hourly")
async def get_hourly_intensity() -> dict[str, Any]:
    """24-hour carbon intensity from 1 AM through 12 AM with scheduling summary."""
    data = await virginia_grid.get_hourly_intensity()
    if data is None:
        raise HTTPException(status_code=503, detail="Unable to fetch hourly intensity data")
    return data


@app.get("/api/v1/carbon/generation-mix", response_model=dict[str, float])
async def get_generation_mix() -> dict[str, float]:
    return await virginia_grid.get_generation_mix()


@app.post("/api/v1/code/analyze", response_model=CodeEnergyResponse)
async def analyze_code(request: CodeAnalysisRequest) -> CodeEnergyResponse:
    intensity = await virginia_grid.get_current_intensity(real_time=True)
    carbon_intensity = intensity["carbon_intensity_g_per_kwh"] if intensity else 400.0

    result = code_estimator.estimate(
        code=request.code,
        language=request.language,
        runtime_seconds=request.runtime_seconds,
        cpu_utilization=request.cpu_utilization,
        memory_mb=request.memory_mb,
        carbon_intensity_g_per_kwh=carbon_intensity,
    )
    return CodeEnergyResponse(
        estimated_energy_kwh=result["energy_kwh"],
        estimated_emissions_g_co2=result["emissions_g_co2"],
        estimated_emissions_lb_co2=result["emissions_lb_co2"],
        carbon_intensity_used_g_per_kwh=carbon_intensity,
        breakdown=result["breakdown"],
        timestamp=datetime.utcnow(),
    )


@app.get("/api/v1/carbon/compare", response_model=HistoricalComparisonResponse)
async def compare_historical(
    days: int = Query(default=30, ge=1, le=365, description="Days of history for comparison"),
) -> HistoricalComparisonResponse:
    current = await virginia_grid.get_current_intensity(real_time=True)
    if current is None:
        raise HTTPException(status_code=503, detail="Unable to fetch current intensity")

    comparison = await historical.compare(
        current_intensity_g_per_kwh=current["carbon_intensity_g_per_kwh"],
        days=days,
    )
    return HistoricalComparisonResponse(**comparison)


@app.get("/api/v1/grid/status", response_model=GridStatusResponse)
async def get_grid_status() -> GridStatusResponse:
    current = await virginia_grid.get_current_intensity(real_time=True)
    forecast = await virginia_grid.get_forecast(hours=24)
    mix = await virginia_grid.get_generation_mix()

    if current is None:
        raise HTTPException(status_code=503, detail="Grid data unavailable")

    return GridStatusResponse(
        region="VA-DOM",
        current_intensity=current,
        forecast=forecast,
        generation_mix=mix,
    )


@app.get("/api/v1/carbon/equivalents")
async def get_emission_equivalents(
    grams_co2: float = Query(default=1000, ge=0, description="CO2 in grams to convert"),
) -> dict[str, Any]:
    return {
        "grams_co2": grams_co2,
        "equivalents": {
            "miles_driven_avg_car": round(grams_co2 / 404, 2),
            "smartphone_charges": round(grams_co2 / 8.5, 1),
            "led_bulb_hours": round(grams_co2 / 0.045, 1),
            "tree_days_to_sequester": round(grams_co2 / 21.9, 2),
            "coal_grams_burned": round(grams_co2 / 2.42, 1),
            "natural_gas_cubic_feet": round(grams_co2 / 54.4, 2),
        },
    }