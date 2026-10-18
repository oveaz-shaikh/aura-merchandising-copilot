
import math

from app.engines.promotions import generate_scenarios
from app.engines.finance import calculate_financials


def optimize_product(
    product,
    brand,
    current_stock,
    baseline_daily_units,
    deadline_days,
    objective="balanced",
    minimum_margin_percent=None,
    max_discount_percent=None,
    target_units=None,
):
    if deadline_days < 1 or deadline_days > 365:
        raise ValueError("deadline_days must be between 1 and 365")
    if objective not in {"clearance", "profit", "balanced"}:
        raise ValueError("objective must be clearance, profit, or balanced")
    if current_stock < 0:
        raise ValueError("current_stock cannot be negative")
    if baseline_daily_units < 0:
        raise ValueError("baseline_daily_units cannot be negative")

    stock = int(current_stock)
    baseline = float(baseline_daily_units)
    target_stock = stock if target_units is None else min(stock, int(target_units))
    if target_stock < 0:
        raise ValueError("target_units cannot be negative")

    # Distinguish total available inventory from the quantity the user wants
    # to clear during this campaign.
    required_daily_units = (
        math.ceil(target_stock / deadline_days) if target_stock > 0 else 0
    )
    baseline_deadline_units = min(
        target_stock, math.floor(baseline * deadline_days)
    )
    baseline_clearance_days = (
        math.ceil(target_stock / baseline)
        if target_stock > 0 and baseline > 0
        else None
    )

    # A request may tighten brand rules, never weaken them.
    brand_min_margin = float(brand.minimum_margin_percent)
    requested_min_margin = (
        brand_min_margin
        if minimum_margin_percent is None
        else float(minimum_margin_percent)
    )
    min_margin = max(brand_min_margin, requested_min_margin)

    scenarios = generate_scenarios(
        product, brand, max_discount_percent
    )
    evaluated = []

    for scenario in scenarios:
        promo_type = scenario["promotion_type"]

        # Illustrative assumptions, not measured campaign effects.
        if promo_type == "discount":
            lift = 1 + float(scenario["discount_percent"]) * 0.045
            reward_cost = 0.0
        elif promo_type == "quantity":
            lift, reward_cost = 1.8, 0.0
        elif promo_type == "bundle":
            lift, reward_cost = 1.35, 0.0
        elif promo_type == "loyalty":
            lift = 1.2
            reward_cost = scenario["mechanic"].get(
                "estimated_reward_cost_per_unit", 2
            )
        else:
            lift = 1.25
            reward_cost = scenario["mechanic"].get(
                "estimated_voucher_or_gift_cost_per_unit", 5
            )

        daily = max(0.0, baseline * lift)

        expected_units = min(
            target_stock,
            int(math.ceil(daily * deadline_days)),
        )

        clearance_days = (
            0
            if target_stock == 0
            else (
                math.ceil(target_stock / daily)
                if daily > 0
                else None
            )
        )

        financials = calculate_financials(
            product,
            scenario,
            expected_units,
            reward_cost_per_unit=reward_cost,
        )

        margin = float(financials["estimated_margin_percent"])
        margin_ok = margin >= min_margin

        deadline_ok = (
            clearance_days is not None
            and clearance_days <= deadline_days
        )

        complementary_missing = bool(
            scenario.get("requires_complementary_inventory")
        )

        unit_cost = float(product.cost_price)
        realized_price = float(scenario["effective_unit_price"])
        price_floor_ok = realized_price >= unit_cost

        eligible = (
            margin_ok
            and price_floor_ok
            and not complementary_missing
        )
        feasible = eligible and deadline_ok

        clearance_ratio = (
            1.0 if target_stock == 0 else expected_units / target_stock
        )

        row = {
            **scenario,
            **financials,
            "estimated_daily_units": round(daily, 2),
            "estimated_clearance_days": clearance_days,
            "expected_stock_remaining": max(
                0, stock - expected_units
            ),
            "target_units": target_stock,
            "estimated_clearance_ratio_percent": round(
                clearance_ratio * 100, 2
            ),
            "meets_deadline": bool(deadline_ok),
            "meets_minimum_margin": bool(margin_ok),
            "meets_unit_cost_floor": bool(price_floor_ok),
            "eligible": bool(eligible),
            "feasible": bool(feasible),
            "estimate_note": (
                "Illustrative heuristic only; promotion uplift is "
                "not trained or causally validated."
            ),
        }
        evaluated.append(row)

    if not evaluated:
        raise ValueError(
            "No promotion scenarios could be generated under "
            "the configured discount cap."
        )

    feasible_pool = [r for r in evaluated if r["feasible"]]
    eligible_pool = [r for r in evaluated if r["eligible"]]

    if feasible_pool:
        pool = feasible_pool
        status = "feasible"
    elif eligible_pool:
        pool = eligible_pool
        status = "fallback_no_deadline_feasible"
    else:
        pool = evaluated
        status = "no_eligible_scenario"

    max_units = max(1, target_stock)
    max_profit = max(
        1.0,
        max(
            0.0,
            max(float(r["estimated_net_profit"]) for r in pool),
        ),
    )

    def score(row):
        units_score = row["expected_units_sold"] / max_units
        profit_score = max(
            0.0, float(row["estimated_net_profit"])
        ) / max_profit

        days = row["estimated_clearance_days"]
        deadline_score = (
            1.0
            if days is not None and days <= deadline_days
            else (
                0.0
                if days is None
                else min(1.0, deadline_days / max(days, 1))
            )
        )

        if objective == "clearance":
            return (
                units_score,
                deadline_score,
                float(row["estimated_net_profit"]),
            )

        if objective == "profit":
            return (
                float(row["estimated_net_profit"]),
                deadline_score,
                units_score,
            )

        balanced_score = (
            0.45 * units_score
            + 0.35 * profit_score
            + 0.20 * deadline_score
        )
        return (
            balanced_score,
            deadline_score,
            float(row["estimated_net_profit"]),
        )

    winner = max(pool, key=score)

    if status == "feasible":
        selection_reason = (
            "Selected from scenarios meeting all modeled constraints."
        )
    elif status == "fallback_no_deadline_feasible":
        selection_reason = (
            "No scenario met the deadline. This fallback meets "
            "the modeled margin and unit-cost requirements, "
            "but is not feasible for the requested deadline."
        )
    else:
        selection_reason = (
            "No scenario meets all eligibility requirements. "
            "The returned scenario is diagnostic only and must "
            "not be treated as an eligible recommendation."
        )

    warning = (
        "A scenario meets all modeled constraints."
        if status == "feasible"
        else (
            "No scenario meets the requested deadline. "
            "The recommendation is a fallback, not a feasible solution."
            if status == "fallback_no_deadline_feasible"
            else (
                "No scenario satisfies all eligibility requirements. "
                "The returned scenario is diagnostic only."
            )
        )
    )

    if stock > 0 and baseline_clearance_days is None:
        clearance_diagnostic = (
            "Baseline demand is zero, so baseline clearance time "
            "cannot be estimated."
        )
    elif stock > 0 and baseline_clearance_days > deadline_days:
        clearance_diagnostic = (
            "Baseline demand is insufficient to clear all stock "
            "within the requested deadline. Promotion uplift values "
            "are illustrative, not validated campaign results."
        )
    else:
        clearance_diagnostic = (
            "Baseline demand is sufficient for the requested "
            "clearance deadline under the current estimate."
        )

    return {
        "sku": product.sku,
        "product_name": product.product_name,
        "brand": brand.name,
        "current_stock": stock,
        "target_units": target_stock,
        "deadline_days": int(deadline_days),

        # New diagnostic fields.
        "required_daily_units_to_clear_stock": required_daily_units,
        "baseline_expected_units_by_deadline": baseline_deadline_units,
        "baseline_estimated_clearance_days": baseline_clearance_days,
        "clearance_gap_units": max(
            0, stock - baseline_deadline_units
        ),
        "clearance_diagnostic": clearance_diagnostic,

        # Existing response fields preserved.
        "objective": objective,
        "minimum_margin_percent": round(min_margin, 2),
        "brand_minimum_margin_percent": round(
            brand_min_margin, 2
        ),
        "scenarios_evaluated": len(evaluated),
        "feasible_scenarios_count": len(feasible_pool),
        "eligible_scenarios_count": len(eligible_pool),
        "has_feasible_recommendation": bool(feasible_pool),
        "recommendation_status": status,
        "selection_reason": selection_reason,
        "recommendation": winner,
        "all_scenarios": sorted(
            evaluated,
            key=lambda r: (
                r["feasible"],
                r["eligible"],
                r["estimated_net_profit"],
            ),
            reverse=True,
        ),
        "warning": warning,
        "methodology_note": (
            "Expected units are capped at available stock. Clearance "
            "days use the estimated daily sales rate against starting "
            "stock. Promotion lifts are illustrative assumptions, not "
            "measured campaign effects. Eligibility requires the minimum "
            "margin, unit-cost floor, and complementary inventory where "
            "needed. Feasibility additionally requires the deadline. "
            "Clearance diagnostics compare required daily sales with "
            "the supplied baseline demand estimate."
        ),
    }
