import pytest
from datetime import datetime, timezone

from app.services.virginia_grid import VirginiaGridService
from app.services.code_energy import CodeEnergyEstimator
from app.services.historical import HistoricalCarbonService


class TestVirginiaGridService:
    @pytest.fixture
    async def service(self):
        svc = VirginiaGridService()
        await svc.initialize()
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_get_current_intensity_fallback(self, service):
        result = await service.get_current_intensity(real_time=False)
        assert result is not None
        assert "carbon_intensity_g_per_kwh" in result
        assert "carbon_intensity_lb_per_mwh" in result
        assert result["region"] == "VA-DOM"
        assert result["is_real_time"] is False
        assert result["carbon_intensity_g_per_kwh"] > 0

    @pytest.mark.asyncio
    async def test_get_historical_intensity(self, service):
        result = await service.get_historical_intensity(hours=24)
        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert "carbon_intensity_g_per_kwh" in item
            assert "timestamp" in item

    @pytest.mark.asyncio
    async def test_get_forecast(self, service):
        result = await service.get_forecast(hours=12)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_generation_mix(self, service):
        result = await service.get_generation_mix()
        assert isinstance(result, dict)
        assert "natural_gas" in result
        assert "nuclear" in result
        total = sum(result.values())
        assert abs(total - 100) < 1.0


class TestCodeEnergyEstimator:
    @pytest.fixture
    def estimator(self):
        return CodeEnergyEstimator()

    def test_estimate_python_code(self, estimator):
        code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

result = fibonacci(30)
"""
        result = estimator.estimate(
            code=code,
            language="python",
            runtime_seconds=None,
            cpu_utilization=0.5,
            memory_mb=256,
            carbon_intensity_g_per_kwh=400.0,
        )
        assert result["energy_kwh"] > 0
        assert result["emissions_g_co2"] > 0
        assert "breakdown" in result
        assert result["breakdown"]["cpu_wh"] > 0

    def test_estimate_different_languages(self, estimator):
        code = """
def compute(n):
    total = 0
    for i in range(n):
        for j in range(n):
            total += i * j
    return total

result = compute(1000)
"""
        languages = ["python", "javascript", "go", "rust", "cpp", "java"]

        results = {}
        for lang in languages:
            result = estimator.estimate(
                code=code,
                language=lang,
                runtime_seconds=None,
                cpu_utilization=0.5,
                memory_mb=256,
                carbon_intensity_g_per_kwh=400.0,
            )
            results[lang] = result["energy_kwh"]

        assert results["rust"] < results["python"]
        assert results["go"] < results["python"]
        assert results["cpp"] < results["python"]

    def test_compare_optimizations(self, estimator):
        original = """
result = []
for i in range(10000):
    result.append(i * 2)
"""
        optimized = """
result = [i * 2 for i in range(10000)]
"""
        comparison = estimator.compare_optimizations(
            original_code=original,
            optimized_code=optimized,
            language="python",
            carbon_intensity_g_per_kwh=400.0,
        )
        assert "savings" in comparison
        assert comparison["savings"]["percent_reduction"] >= 0


class TestHistoricalCarbonService:
    @pytest.fixture
    async def service(self):
        svc = HistoricalCarbonService()
        await svc.initialize()
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_compare_current_to_historical(self, service):
        result = await service.compare(current_intensity_g_per_kwh=400.0, days=30)
        assert "current_intensity_g_per_kwh" in result
        assert "historical_avg_g_per_kwh" in result
        assert "percentile" in result
        assert 0 <= result["percentile"] <= 100

    @pytest.mark.asyncio
    async def test_get_time_series(self, service):
        result = await service.get_time_series(days=7)
        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert "timestamp" in item
            assert "carbon_intensity_g_per_kwh" in item

    @pytest.mark.asyncio
    async def test_get_daily_averages(self, service):
        result = await service.get_daily_averages(days=7)
        assert isinstance(result, list)
        for item in result:
            assert "date" in item
            assert "avg_intensity_g_per_kwh" in item

    @pytest.mark.asyncio
    async def test_get_percentile_rank(self, service):
        result = await service.get_percentile_rank(400.0, days=30)
        assert 0 <= result <= 100