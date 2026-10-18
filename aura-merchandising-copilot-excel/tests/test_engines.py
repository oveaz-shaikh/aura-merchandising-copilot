from types import SimpleNamespace
from app.engines.finance import calculate_financials
from app.engines.promotions import generate_scenarios

def test_financial_calculation():
    product = SimpleNamespace(cost_price=40, selling_price=100)
    scenario = {"effective_unit_price":80}
    result = calculate_financials(product, scenario, 10)
    assert result["expected_revenue"] == 800
    assert result["cost_of_goods_sold"] == 400
    assert result["estimated_net_profit"] == 400

def test_five_promotion_families_present():
    product = SimpleNamespace(selling_price=100)
    brand = SimpleNamespace(max_discount_percent=30)
    scenarios = generate_scenarios(product, brand)
    types = {s["promotion_type"] for s in scenarios}
    assert {"discount","quantity","bundle","loyalty","voucher_gift"}.issubset(types)

def test_excel_workbook_exists_and_validates():
    from app.excel_store import store
    assert store.validate() is True
    assert len(store.products()) >= 1


def test_forecast_returns_holdout_metrics():
    from app.engines.forecast import forecast_sku
    from app.excel_store import store
    result = forecast_sku(store.sales(), "AE-POLO-001", 14)
    assert result["horizon_days"] == 14
    assert len(result["forecast"]) == 14
    assert result["evaluation"]["test_days"] >= 7
    assert result["evaluation"]["model_mae_units"] >= 0
    assert "seasonal_naive_mae_units" in result["evaluation"]


def test_forecast_includes_recent_average_baseline():
    from app.engines.forecast import forecast_sku
    from app.excel_store import store
    result = forecast_sku(store.sales(), "AE-POLO-001", 30)
    assert "recent_28_day_average_mae_units" in result["evaluation"]
    assert "model_beats_recent_average_on_mae" in result["evaluation"]
    assert isinstance(result["forecast_units_total"], (int, float))
    assert all(isinstance(row["predicted_units"], (int, float)) for row in result["forecast"])


def test_optimizer_accepts_forecast_average_as_baseline():
    from app.engines.optimizer import optimize_product
    from app.excel_store import store
    product = store.product("AE-POLO-001")
    brand = store.brand(product.brand_id)
    result = optimize_product(product, brand, store.stock(product.sku), 1.05, 30, "balanced")
    assert result["sku"] == "AE-POLO-001"
    assert result["recommendation"]["estimated_daily_units"] >= 0
    assert "has_feasible_recommendation" in result


def test_forecast_selects_best_holdout_method():
    from app.engines.forecast import forecast_sku
    from app.excel_store import store
    result = forecast_sku(store.sales(), "AE-POLO-001", 14)
    evaluation = result["evaluation"]
    assert result["selected_forecast_method"] in {
        "hist_gradient_boosting", "seasonal_naive", "recent_28_day_average"
    }
    assert evaluation["selected_method_mae_units"] <= min(
        evaluation["model_mae_units"],
        evaluation["seasonal_naive_mae_units"],
        evaluation["recent_28_day_average_mae_units"],
    ) + 0.001


def test_optimizer_flags_unit_cost_floor():
    from app.engines.optimizer import optimize_product
    from app.excel_store import store
    product = store.product("AE-POLO-001")
    brand = store.brand(product.brand_id)
    result = optimize_product(product, brand, store.stock(product.sku), 1.05, 30, "balanced")
    for scenario in result["all_scenarios"]:
        if scenario["effective_unit_price"] < product.cost_price:
            assert scenario["meets_unit_cost_floor"] is False
            assert scenario["eligible"] is False
