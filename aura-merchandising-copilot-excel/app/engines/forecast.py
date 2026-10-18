
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error


FEATURES = [
    "lag_1",
    "lag_7",
    "rolling_mean_7",
    "rolling_mean_28",
    "day_of_week",
    "day_index",
]

MODEL_PARAMS = {
    "max_iter": 120,
    "learning_rate": 0.06,
    "max_leaf_nodes": 7,
    "l2_regularization": 1.0,
    "random_state": 42,
}

TEST_DAYS_PER_FOLD = 7
MAX_BACKTEST_FOLDS = 4
MIN_TRAIN_ROWS = 28


def _daily_series(sales: pd.DataFrame, sku: str) -> pd.Series:
    """Create a continuous daily series from recorded SKU sales."""
    required = {"sale_date", "sku", "units_sold"}
    missing = required.difference(sales.columns)
    if missing:
        raise ValueError(
            f"Sales sheet is missing required columns: {sorted(missing)}"
        )

    df = sales.loc[
        sales["sku"].astype(str) == str(sku),
        ["sale_date", "units_sold"],
    ].copy()

    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce")
    df = df.dropna(subset=["sale_date", "units_sold"])

    if df.empty:
        raise ValueError(f"No usable sales history found for SKU {sku}.")

    if (df["units_sold"] < 0).any():
        raise ValueError("Sales units cannot be negative.")

    df["sale_date"] = df["sale_date"].dt.normalize()
    daily = df.groupby("sale_date")["units_sold"].sum().sort_index()

    # Preserve the existing data assumption and disclose it in the response.
    dates = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    return daily.reindex(dates, fill_value=0.0).astype(float)


def _features(series: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(index=series.index)
    frame["lag_1"] = series.shift(1)
    frame["lag_7"] = series.shift(7)
    frame["rolling_mean_7"] = (
        series.shift(1).rolling(7, min_periods=7).mean()
    )
    frame["rolling_mean_28"] = (
        series.shift(1).rolling(28, min_periods=28).mean()
    )
    frame["day_of_week"] = series.index.dayofweek
    frame["day_index"] = np.arange(len(series), dtype=float)
    return frame


def _wape(actual, predicted) -> float | None:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denominator = float(np.abs(actual).sum())

    if denominator <= 0:
        return None

    return round(
        float(np.abs(actual - predicted).sum() / denominator * 100),
        2,
    )


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(**MODEL_PARAMS)


def _backtest(dataset: pd.DataFrame) -> dict:
    """Evaluate all methods across expanding-window chronological folds."""
    n = len(dataset)
    fold_size = TEST_DAYS_PER_FOLD

    # Use as many folds as the available history safely supports.
    possible_folds = (n - MIN_TRAIN_ROWS) // fold_size
    fold_count = min(MAX_BACKTEST_FOLDS, possible_folds)

    if fold_count < 1:
        raise ValueError(
            "Not enough history for multi-period backtesting. "
            "Collect more daily sales data for this SKU."
        )

    first_test_start = n - fold_count * fold_size

    actual_all = []
    model_all = []
    seasonal_all = []
    recent_all = []

    for fold in range(fold_count):
        test_start = first_test_start + fold * fold_size
        test_end = test_start + fold_size

        train = dataset.iloc[:test_start]
        test = dataset.iloc[test_start:test_end]

        if len(train) < MIN_TRAIN_ROWS or test.empty:
            continue

        model = _new_model()
        model.fit(train[FEATURES], train["target"])
        model_pred = np.maximum(
            0.0, model.predict(test[FEATURES])
        )

        seasonal_pred = np.maximum(
            0.0, test["lag_7"].to_numpy(dtype=float)
        )
        recent_pred = np.maximum(
            0.0, test["rolling_mean_28"].to_numpy(dtype=float)
        )

        actual_all.extend(test["target"].to_numpy(dtype=float))
        model_all.extend(model_pred)
        seasonal_all.extend(seasonal_pred)
        recent_all.extend(recent_pred)

    if not actual_all:
        raise ValueError("Unable to create usable chronological test folds.")

    actual = np.asarray(actual_all, dtype=float)
    predictions = {
        "hist_gradient_boosting": np.asarray(model_all, dtype=float),
        "seasonal_naive": np.asarray(seasonal_all, dtype=float),
        "recent_28_day_average": np.asarray(recent_all, dtype=float),
    }

    metrics = {}
    for name, predicted in predictions.items():
        metrics[name] = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "wape": _wape(actual, predicted),
        }

    return {
        "metrics": metrics,
        "fold_count": fold_count,
        "test_days": len(actual),
    }


def forecast_sku(
    sales: pd.DataFrame,
    sku: str,
    horizon_days: int = 30,
) -> dict:
    """Forecast one SKU using multi-period chronological model selection."""
    if horizon_days < 1 or horizon_days > 90:
        raise ValueError("horizon_days must be between 1 and 90")

    series = _daily_series(sales, sku)

    if len(series) < 45:
        raise ValueError("At least 45 calendar days of sales history are required.")

    features = _features(series)
    dataset = features.copy()
    dataset["target"] = series
    dataset = dataset.dropna()

    if len(dataset) < MIN_TRAIN_ROWS + TEST_DAYS_PER_FOLD:
        raise ValueError(
            "Not enough usable lagged observations for backtesting."
        )

    backtest = _backtest(dataset)
    metrics = backtest["metrics"]

    # Choose the lowest average MAE across all chronological test folds.
    # Prefer a simple baseline in an exact tie.
    tie_priority = {
        "seasonal_naive": 0,
        "recent_28_day_average": 1,
        "hist_gradient_boosting": 2,
    }
    selected_method = min(
        metrics,
        key=lambda name: (
            metrics[name]["mae"],
            tie_priority[name],
        ),
    )

    final_model = None
    if selected_method == "hist_gradient_boosting":
        final_model = _new_model()
        final_model.fit(dataset[FEATURES], dataset["target"])

    history = series.copy()
    future_rows = []
    static_recent_mean = float(series.iloc[-28:].mean())

    for _ in range(horizon_days):
        next_date = history.index[-1] + pd.Timedelta(days=1)
        values = history.to_numpy(dtype=float)

        if selected_method == "seasonal_naive":
            prediction = float(values[-7])

        elif selected_method == "recent_28_day_average":
            prediction = static_recent_mean

        else:
            row = {
                "lag_1": float(values[-1]),
                "lag_7": float(values[-7]),
                "rolling_mean_7": float(np.mean(values[-7:])),
                "rolling_mean_28": float(np.mean(values[-28:])),
                "day_of_week": int(next_date.dayofweek),
                "day_index": float(len(history)),
            }
            prediction = float(
                final_model.predict(
                    pd.DataFrame([row], columns=FEATURES)
                )[0]
            )

        prediction = round(max(0.0, prediction), 2)
        future_rows.append({
            "date": next_date.date().isoformat(),
            "predicted_units": prediction,
        })
        history.loc[next_date] = prediction

    total_forecast = round(
        sum(row["predicted_units"] for row in future_rows), 2
    )

    model_mae = metrics["hist_gradient_boosting"]["mae"]
    seasonal_mae = metrics["seasonal_naive"]["mae"]
    recent_mae = metrics["recent_28_day_average"]["mae"]

    caveats = [
        "Historical sales are synthetic demo data with a limited time window.",
        "Model selection uses expanding-window chronological backtesting; "
        "performance can vary by SKU and future period.",
        "Forecast units are expected values and may be fractional.",
        "Future predictions are recursive for the machine-learning and "
        "seasonal-naive methods.",
        "Promotion uplift is not learned from this forecast; no observed "
        "campaign outcomes are available in the supplied workbook.",
        "Missing sales dates are treated as zero recorded sales, which may "
        "not represent true zero demand.",
        "Stockouts and unavailable inventory can censor observed demand.",
        "WAPE can be high for intermittent sales; review MAE and WAPE together.",
    ]

    if selected_method != "hist_gradient_boosting":
        caveats.append(
            f"The {selected_method} baseline had the lowest backtest MAE "
            "and was selected instead of HistGradientBoosting."
        )

    return {
        "sku": str(sku),
        "history_start": series.index.min().date().isoformat(),
        "history_end": series.index.max().date().isoformat(),
        "history_days": int(len(series)),
        "horizon_days": int(horizon_days),
        "forecast_units_total": total_forecast,
        "average_forecast_units_per_day": round(
            total_forecast / horizon_days, 2
        ),
        "selected_forecast_method": selected_method,
        "forecast": future_rows,
        "evaluation": {
            "method": "expanding_window_chronological_backtest",
            "fold_count": backtest["fold_count"],
            "test_days": backtest["test_days"],
            "model": "hist_gradient_boosting",
            "selected_forecast_method": selected_method,
            "model_mae_units": round(model_mae, 3),
            "seasonal_naive_mae_units": round(seasonal_mae, 3),
            "model_wape_percent": metrics["hist_gradient_boosting"]["wape"],
            "seasonal_naive_wape_percent": metrics["seasonal_naive"]["wape"],
            "recent_28_day_average_mae_units": round(recent_mae, 3),
            "recent_28_day_average_wape_percent": (
                metrics["recent_28_day_average"]["wape"]
            ),
            "selected_method_mae_units": round(
                metrics[selected_method]["mae"], 3
            ),
            "selected_method_wape_percent": metrics[selected_method]["wape"],
            "model_beats_seasonal_naive_on_mae": bool(
                model_mae < seasonal_mae
            ),
            "model_beats_recent_average_on_mae": bool(
                model_mae < recent_mae
            ),
        },
        "data_basis": "synthetic demo Excel Sales sheet",
        "caveats": caveats,
    }
