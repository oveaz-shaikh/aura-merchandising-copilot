# Forecast and optimizer improvements

## Changes

- Forecasting now evaluates HistGradientBoosting, seasonal-naive, and recent-28-day-average methods on the same chronological holdout.
- The method with the lowest holdout MAE is selected for the future forecast. The response reports the selected method and its MAE/WAPE as well as the individual baselines.
- Existing forecast fields and API routes are preserved; new evaluation fields are additive.
- The optimizer now explicitly checks the average realized unit price against the product's unit cost. A scenario below unit cost is marked `meets_unit_cost_floor=false` and cannot be eligible.
- The optimization response includes the selected forecast method in `forecast_summary`.
- Added tests for forecast-method selection and optimizer cost-floor enforcement.

## Verification

Run from the project folder with the existing virtual environment activated:

```powershell
python -m pytest -q
```

Expected result for this source snapshot: `8 passed`.

Start the API:

```powershell
uvicorn app.main:app --reload
```

Test forecast:

`GET http://127.0.0.1:8000/api/forecast?sku=AE-POLO-001&horizon_days=30`

Inspect `selected_forecast_method` and `evaluation.selected_method_mae_units` / `evaluation.selected_method_wape_percent`.

Test optimizer using the existing request body:

```json
{
  "sku": "AE-POLO-001",
  "deadline_days": 30,
  "objective": "balanced",
  "minimum_margin_percent": 20,
  "max_discount_percent": 30
}
```

Inspect `recommendation.meets_unit_cost_floor`, `recommendation.meets_deadline`, `recommendation.feasible`, and `has_feasible_recommendation`.

## Important limitations

- The workbook contains synthetic demo data and a short history.
- Missing dates are still interpreted as zero recorded sales; this needs validation against real store reporting semantics.
- The model selection is based on one chronological holdout. For a stronger assessment, use rolling-origin backtesting over several cutoffs.
- Promotion lifts remain heuristic because the workbook has no observed campaign outcomes. Do not treat them as causal estimates.
- A scenario can meet the unit-cost floor and minimum margin while still failing to clear stock by the deadline.
