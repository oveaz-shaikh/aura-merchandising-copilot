# Aura Merchandising Copilot — Excel Edition

This version uses `data/aura_retail_data.xlsx` as the primary application data source. SQLite/SQLAlchemy are not required.

## Excel workbook sheets
- Brands
- Products
- Inventory
- Sales
- Promotion_Rules
- Promotion_History
- Loyalty
- Campaign_Results

All included records are synthetic demo data.

## Setup on Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
Add your Groq/Gemini keys to `.env`. Only Groq and Gemini are supported.

Validate the workbook:
```powershell
python -m app.seed_data
```

Start API:
```powershell
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000/docs`.

## Test order
1. GET `/health` — confirm `data_source: excel` and `excel_valid: true`.
2. GET `/api/brands`.
3. GET `/api/products`; copy a real SKU.
4. GET `/api/dead-stock`.
5. POST `/api/optimize` using that SKU.
6. POST `/api/chat` after adding a valid Groq or Gemini key.

## Editing data
Close Excel before making API requests if your Windows/Excel setup locks the workbook. Keep sheet names and header names unchanged. The app reloads sheets on each request, so saved Excel changes are picked up without rebuilding a database.

## Important prototype limitations
The promotion lift/clearance logic is currently a transparent heuristic scaffold, not a trained causal promotion-response model. XGBoost is included as a dependency for the planned forecasting stage, but the current optimizer does not yet use a trained XGBoost forecast. Marketing RAG currently uses local knowledge documents; Gemini embedding/vector retrieval is a next-stage enhancement. Financial outputs are estimates and should not be treated as guaranteed business outcomes.


## Demand forecasting endpoint (prototype)

`GET /api/forecast?sku=AE-POLO-001&horizon_days=30` returns a SKU-level daily forecast,
a chronological holdout evaluation, and a seasonal-naive benchmark. The forecast uses
historical sales features (lags, rolling averages, weekday and time index). It does not
estimate causal promotion lift. The supplied workbook is synthetic, has only about 120
days of history, and has no campaign-result observations, so forecasts must be treated
as prototype estimates. A missing date in the sales rows is treated as zero recorded sales.


## Forecast evaluation update

The forecast endpoint now retains fractional expected demand during recursive forecasting
instead of rounding each predicted day to a whole unit. This avoids a rounding feedback loop
that can produce a flat 1-unit-per-day forecast. It also evaluates the model against both
the previous-week seasonal-naive baseline and a rolling recent-28-day-average baseline.

Forecast values are expected units, not guaranteed integer sales. This is still a prototype:
synthetic history is limited, WAPE remains relatively high, and promotion lift is not learned
from the empty Campaign_Results sheet. Review the evaluation metrics before operational use.


## Forecast-integrated optimization

`POST /api/optimize` now tries to use the SKU-level forecast average as its baseline demand rate.
For deadlines over 90 days, the baseline uses the average daily rate from a 90-day forecast because
the forecasting endpoint is limited to 90 days. If forecasting fails for insufficient or invalid
history, the API falls back to the recent 30-day sales rate and identifies that source in the response.
Promotion-lift multipliers remain illustrative assumptions; the baseline model does not learn causal
promotion effects. The chat endpoint receives the same forecast-source and evaluation context.
