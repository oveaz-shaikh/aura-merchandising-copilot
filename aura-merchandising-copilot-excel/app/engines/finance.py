
def calculate_financials(
    product,
    scenario,
    expected_units,
    reward_cost_per_unit=0.0,
    extra_campaign_cost=0.0,
):
    """Estimate SKU-level promotion economics.

    Quantity promotions use paid/free/discounted unit mechanics when
    supplied. Results are estimates, not measured campaign outcomes.
    """
    units = max(0, int(expected_units))
    price = max(0.0, float(product.selling_price))
    print("PRICE DEBUG:", price)
    unit_cost = max(0.0, float(product.cost_price))
    promo_type = scenario.get("promotion_type", "")
    print("FINANCE DEBUG:", promo_type, scenario.get("mechanic"), expected_units)
    mechanic = scenario.get("mechanic", {})

    # Revenue calculation
    if promo_type == "quantity":
        paid_units_per_offer = int(mechanic.get("paid_units", 0))
        free_units_per_offer = int(mechanic.get("free_units", 0))
        third_discount = float(
            mechanic.get("third_unit_discount_percent", 0)
        )

        if paid_units_per_offer > 0 and free_units_per_offer > 0:
            offer_size = paid_units_per_offer + free_units_per_offer
            complete_offers = units // offer_size
            remaining_units = units % offer_size

            revenue = (
                complete_offers * paid_units_per_offer * price
                + remaining_units * price
            )
        elif paid_units_per_offer > 0 and third_discount > 0:
            offer_size = paid_units_per_offer + 1
            complete_offers = units // offer_size
            remaining_units = units % offer_size

            discounted_third_price = price * (1 - third_discount / 100)

            revenue = (
                complete_offers
                * (paid_units_per_offer * price + discounted_third_price)
                + remaining_units * price
            )
        else:
            effective_price = max(
                0.0, float(scenario["effective_unit_price"])
            )
            revenue = effective_price * units
    else:
        effective_price = max(
            0.0, float(scenario["effective_unit_price"])
        )
        revenue = effective_price * units

    cogs = unit_cost * units
    reward_cost = max(0.0, float(reward_cost_per_unit)) * units
    campaign_cost = max(0.0, float(extra_campaign_cost))
    promo_cost = reward_cost + campaign_cost
    net_profit = revenue - cogs - promo_cost
    margin = net_profit / revenue * 100.0 if revenue > 0 else 0.0

    return {
        "expected_units_sold": units,
        "effective_unit_price": round(
            revenue / units if units > 0 else 0.0, 2
        ),
        "expected_revenue": round(revenue, 2),
        "cost_of_goods_sold": round(cogs, 2),
        "estimated_promotion_cost": round(promo_cost, 2),
        "estimated_net_profit": round(net_profit, 2),
        "estimated_margin_percent": round(margin, 2),
        "financial_note": (
            "SKU-level estimates exclude tax, returns, fixed costs and "
            "unmodeled basket effects. Quantity promotions account for "
            "configured paid/free/discounted units when available. "
            "Loyalty and gift costs depend on supplied cost assumptions."
        ),
    }
