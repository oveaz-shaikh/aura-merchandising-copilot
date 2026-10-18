PROMOTION_TYPES = ["discount", "quantity", "bundle", "loyalty", "voucher_gift"]


def generate_scenarios(product, brand, max_discount_percent=None):
    """Generate only scenarios that respect the strictest configured discount cap."""
    brand_cap = max(0.0, float(brand.max_discount_percent))
    requested_cap = brand_cap if max_discount_percent is None else max(0.0, float(max_discount_percent))
    cap = min(brand_cap, requested_cap)
    price = max(0.0, float(product.selling_price))
    scenarios = []

    for pct in [5, 10, 15, 20, 25, 30]:
        if pct <= cap:
            scenarios.append({
                "promotion_type": "discount",
                "label": f"{pct}% discount",
                "discount_percent": pct,
                "effective_unit_price": round(price * (1 - pct / 100), 2),
                "mechanic": {"discount_percent": pct},
                "requires_complementary_inventory": False,
            })

    # The effective price is averaged over every unit in the offer.
    quantity_scenarios = [
        {
            "promotion_type": "quantity",
            "label": "Buy 2 Get 1 Free",
            "discount_percent": 100 / 3,
            "effective_unit_price": round(price * 2 / 3, 2),
            "mechanic": {"paid_units": 2, "free_units": 1},
            "requires_complementary_inventory": False,
        },
        {
            "promotion_type": "quantity",
            "label": "Buy 2 Get 30% Off Third",
            "discount_percent": 10,
            "effective_unit_price": round(price * 0.9, 2),
            "mechanic": {"paid_units": 2, "third_unit_discount_percent": 30},
            "requires_complementary_inventory": False,
        },
    ]
    scenarios.extend(s for s in quantity_scenarios if s["discount_percent"] <= cap)

    # Do not recommend an unverified cross-product bundle as if its economics were known.
    scenarios.append({
        "promotion_type": "bundle",
        "label": "T-shirt + complementary item bundle",
        "discount_percent": 10,
        "effective_unit_price": round(price * 0.9, 2),
        "mechanic": {"bundle_discount_percent": 10, "requires_complementary_inventory": True},
        "requires_complementary_inventory": True,
        "scenario_warning": "Not financially validated: complementary SKU price, cost and stock are not supplied to this calculation.",
    }) if 10 <= cap else None

    scenarios.extend([
        {
            "promotion_type": "loyalty",
            "label": "Double loyalty points",
            "discount_percent": 0,
            "effective_unit_price": round(price, 2),
            "mechanic": {"points_multiplier": 2, "estimated_reward_cost_per_unit": 2},
            "requires_complementary_inventory": False,
        },
        {
            "promotion_type": "voucher_gift",
            "label": "Spend threshold voucher / gift",
            "discount_percent": 0,
            "effective_unit_price": round(price, 2),
            "mechanic": {"estimated_voucher_or_gift_cost_per_unit": 5},
            "requires_complementary_inventory": False,
        },
    ])
    return scenarios
