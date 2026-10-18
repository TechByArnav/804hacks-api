# CarbonSense — Virginia Grid Carbon API

FastAPI service providing real-time Virginia (Dominion Energy/PJM) grid carbon intensity, code energy/emissions estimation, and historical comparisons.

## Features

- **Real-time carbon intensity** from PJM (VA-DOM zone) — lb CO₂/MWh & g CO₂/kWh
- **Code energy estimation** — analyze source code for energy consumption & emissions across 11 languages
- **Historical comparisons** — percentile ranking vs 30/90/365-day baselines
- **Generation mix** — current VA grid fuel breakdown (gas, nuclear, coal, solar, wind, hydro)
- **Forecast** — 24-72hr carbon intensity projections
- **Emission equivalents** — translate grams CO₂ to relatable metrics (miles driven, phone charges, etc.)

## Quick Start

```bash
cd carbonsense-api
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp .env.example .env  # Add API keys for real-time data
python run.py
```

Server runs at `http://localhost:8000` — API docs at `http://localhost:8000/docs`

## API Endpoints

### Carbon Intensity
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/carbon/intensity` | Current VA grid carbon intensity |
| GET | `/api/v1/carbon/intensity/history?hours=24` | Historical intensity (5-min intervals) |
| GET | `/api/v1/carbon/forecast?hours=24` | 24-72hr forecast |
| GET | `/api/v1/carbon/generation-mix` | Current VA generation fuel mix % |

### Code Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/code/analyze` | Estimate energy & emissions for code snippet |

**Request:**
```json
{
  "code": "def fib(n): return n if n<=1 else fib(n-1)+fib(n-2)\nfib(30)",
  "language": "python",
  "runtime_seconds": null,
  "cpu_utilization": 0.5,
  "memory_mb": 256
}
```

**Response:**
```json
{
  "estimated_energy_kwh": 0.000123,
  "estimated_emissions_g_co2": 0.049,
  "estimated_emissions_lb_co2": 0.000108,
  "carbon_intensity_used_g_per_kwh": 400.0,
  "breakdown": {"cpu_wh": 0.123, "memory_wh": 0.005, ...},
  "timestamp": "2026-10-18T..."
}
```

### Historical & Comparison
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/carbon/compare?days=30` | Current vs historical percentile |
| GET | `/api/v1/grid/status` | Full grid status (current + forecast + mix) |
| GET | `/api/v1/carbon/equivalents?grams_co2=1000` | CO₂ equivalents |

## Supported Languages

Python, JavaScript, TypeScript, Java, Go, Rust, C++, C, C#, Ruby, PHP

## Data Sources

- **PJM API** — Real-time & historical emissions for DOM zone
- **EIA API** — Generation mix by fuel type
- **WattTime** — Alternative carbon intensity (optional)
- **Synthetic fallback** — Realistic modeled data when APIs unavailable

## Testing

```bash
pytest -v
```

## Deployment

```bash
docker build -t carbonsense-api .
docker run -p 8000:8000 --env-file .env carbonsense-api
```

## License

MIT — Built for 804 Hacks 2026

## Landing Page

The project includes a **Phantom Studios–style landing page** at `/landing/` (or deploy to GitHub Pages via the `pages.yml` workflow).

```bash
# Serve locally with API
python run.py
# Visit http://localhost:8000/landing/
```

The landing page includes:
- Hero with CarbonSense brand lockup
- Feature overview cards
- Complete API reference with request/response examples
- Quick start guide
- Project structure