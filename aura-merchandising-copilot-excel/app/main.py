import re
import pandas as pd
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.excel_store import store
from app.engines.dead_stock import dead_stock_report
from app.engines.optimizer import optimize_product
from app.engines.forecast import forecast_sku
from app.services.ai_service import grounded_answer
from app.config import MAX_CHAT_CHARS, EXCEL_FILE


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.validate()
    yield


app = FastAPI(
    title="Aura Merchandising Copilot",
    version="0.2.0",
    description=(
        "Multi-brand retail decision-support prototype using Excel "
        "as the primary data source."
    ),
    lifespan=lifespan,
)

# Allow the local frontend to communicate with FastAPI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OptimizeRequest(BaseModel):
    sku: str = Field(min_length=2, max_length=40)
    deadline_days: int = Field(default=30, ge=1, le=365)
    objective: str = Field(default="balanced")
    minimum_margin_percent: float | None = Field(
        default=None, ge=0, le=95
    )
    max_discount_percent: float | None = Field(
        default=None, ge=0, le=80
    )
    target_units: int | None = Field(default=None, ge=1)

    @field_validator("objective")
    @classmethod
    def objective_allowed(cls, value):
        if value not in {"clearance", "profit", "balanced"}:
            raise ValueError(
                "objective must be clearance, profit, or balanced"
            )
        return value


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=MAX_CHAT_CHARS,
    )
    sku: str | None = Field(default=None, max_length=40)
    deadline_days: int = Field(default=30, ge=1, le=365)
    objective: str = "balanced"
    target_units: int | None = Field(default=None, ge=1)


@app.get("/health")
def health():
    try:
        store.validate()
        excel_ok = True
    except Exception:
        excel_ok = False

    return {
        "status": "ok" if excel_ok else "degraded",
        "app": "Aura Merchandising Copilot",
        "data_source": "excel",
        "excel_file": EXCEL_FILE,
        "excel_valid": excel_ok,
        "supported_llm_providers": ["groq", "gemini"],
        "demo_data": True,
        "note": "Synthetic demo data. No real campaigns are executed.",
    }


@app.get("/api/brands")
def list_brands():
    return [brand.__dict__ for brand in store.brands()]


@app.get("/api/products")
def list_products(brand_id: str | None = None):
    result = []

    for product in store.products(brand_id):
        brand = store.brand(product.brand_id)

        result.append({
            "sku": product.sku,
            "product_name": product.product_name,
            "brand": brand.name if brand else None,
            "brand_id": product.brand_id,
            "category": product.category,
            "cost_price": product.cost_price,
            "selling_price": product.selling_price,
            "launch_date": product.launch_date.isoformat(),
            "current_stock": store.stock(product.sku),
        })

    return result


@app.get("/api/forecast")
def get_forecast(sku: str, horizon_days: int = 30):
    if horizon_days < 1 or horizon_days > 90:
        raise HTTPException(
            status_code=422,
            detail="horizon_days must be between 1 and 90.",
        )

    if not store.product(sku):
        raise HTTPException(
            status_code=404,
            detail="SKU not found. Choose a SKU from /api/products.",
        )

    try:
        return forecast_sku(store.sales(), sku, horizon_days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/dead-stock")
def get_dead_stock():
    return dead_stock_report(store)


@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    product = store.product(req.sku)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="SKU not found in the Excel catalog.",
        )

    brand = store.brand(product.brand_id)
    stock = store.stock(req.sku)

    if stock <= 0:
        raise HTTPException(
            status_code=400,
            detail="No available stock for this SKU.",
        )

    last30 = store.last30_units(req.sku)
    baseline_daily = max(last30 / 30, 0.1)
    forecast_summary = None
    forecast_status = "historical_fallback"

    # Forecasts are limited to 90 days, even when the optimization
    # deadline is longer.
    forecast_horizon = min(req.deadline_days, 90)

    try:
        forecast_summary = forecast_sku(
            store.sales(),
            req.sku,
            forecast_horizon,
        )
        baseline_daily = max(
            0.0,
            float(
                forecast_summary[
                    "average_forecast_units_per_day"
                ]
            ),
        )
        forecast_status = "forecast_model"

    except (ValueError, KeyError, TypeError) as exc:
        forecast_summary = {
            "status": "unavailable",
            "reason": str(exc),
            "fallback": "recent_30_day_sales_rate",
        }

    try:
        result = optimize_product(
            product,
            brand,
            stock,
            baseline_daily,
            req.deadline_days,
            req.objective,
            req.minimum_margin_percent,
            req.max_discount_percent,
            req.target_units,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    result["data_basis"] = "synthetic demo Excel data"
    result["baseline_daily_sales_30d"] = round(last30 / 30, 2)
    result["baseline_demand_source"] = forecast_status

    result["forecast_summary"] = {
        "horizon_days_used": (
            forecast_horizon
            if forecast_status == "forecast_model"
            else None
        ),
        "forecast_units_total": (
            forecast_summary.get("forecast_units_total")
            if forecast_status == "forecast_model"
            else None
        ),
        "average_forecast_units_per_day": round(
            baseline_daily, 3
        ),
        "selected_forecast_method": (
            forecast_summary.get("selected_forecast_method")
            if forecast_status == "forecast_model"
            else None
        ),
        "evaluation": (
            forecast_summary.get("evaluation")
            if forecast_status == "forecast_model"
            else None
        ),
        "caveats": (
            forecast_summary.get("caveats", [])
            if forecast_status == "forecast_model"
            else [
                forecast_summary.get(
                    "reason",
                    "Forecast unavailable; recent sales rate used.",
                )
            ]
        ),
    }

    result["methodology_note"] += (
        " Baseline demand uses the SKU forecast when available; "
        "otherwise it falls back to the recent 30-day sales rate. "
        "Forecast horizon is limited to 90 days, and this forecast "
        "does not estimate causal promotion uplift."
    )

    return result



@app.post("/api/chat")
def chat(req: ChatRequest):
    # Always provide verified data from the Excel workbook.
    context = {
        "demo_data": True,
        "data_source": "Excel",
        "request": {
            "deadline_days": req.deadline_days,
            "objective": req.objective,
            "target_units": req.target_units,
        },
        "scope": (
            "Use the supplied Excel business data and retrieved local "
            "knowledge. Do not invent stock, sales, prices, product names, "
            "or dead-stock classifications. Clearly state when a value "
            "cannot be verified. Demo data is synthetic."
        ),
    }

    # 1. Include the actual dead-stock report.
    try:
        context["dead_stock_report"] = dead_stock_report(store)
    except (ValueError, KeyError, TypeError) as exc:
        context["dead_stock_report"] = {
            "status": "unavailable",
            "reason": str(exc),
        }

    # 2. Include the real product catalog and inventory.
    products_context = []

    for product in store.products():
        brand = store.brand(product.brand_id)

        try:
            stock = store.stock(product.sku)
        except (ValueError, KeyError, TypeError):
            stock = None

        try:
            last30 = store.last30_units(product.sku)
        except (ValueError, KeyError, TypeError):
            last30 = None

        products_context.append({
            "sku": product.sku,
            "product_name": product.product_name,
            "brand": brand.name if brand else None,
            "brand_id": product.brand_id,
            "category": product.category,
            "sub_category": product.sub_category,
            "cost_price": product.cost_price,
            "selling_price": product.selling_price,
            "current_stock": stock,
            "units_sold_last_30_days": last30,
            "historical_average_daily_sales": (
                round(last30 / 30, 2)
                if last30 is not None
                else None
            ),
            "launch_date": product.launch_date.isoformat(),
        })

    context["product_catalog"] = products_context

    # 3. Include a summary of historical sales.
    try:
        sales_df = store.sales()
        sales_df["units_sold"] = pd.to_numeric(
            sales_df["units_sold"], errors="coerce"
        ).fillna(0)

        sales_summary = {
            "total_recorded_units_sold": int(
                sales_df["units_sold"].sum()
            ),
            "products_with_sales_records": int(
                sales_df.loc[
                    sales_df["units_sold"] > 0, "sku"
                ].nunique()
            ),
            "stores_with_sales_records": int(
                sales_df["store"].nunique()
            ),
        }

        context["sales_summary"] = sales_summary

    except (ValueError, KeyError, TypeError) as exc:
        context["sales_summary"] = {
            "status": "unavailable",
            "reason": str(exc),
        }

    # 4. Resolve a SKU from the explicit field or the user's message.
    # This lets the frontend send a normal natural-language question.
    selected_sku = req.sku
    if not selected_sku:
        message_upper = req.message.upper()
        for catalog_product in store.products():
            if re.search(
                rf"(?<![A-Z0-9]){re.escape(catalog_product.sku.upper())}(?![A-Z0-9])",
                message_upper,
            ):
                selected_sku = catalog_product.sku
                break

    # Infer a requested quantity such as "clear 200 units" or "stock of 197".
    target_units = req.target_units
    if target_units is None:
        quantity_match = re.search(
            r"(?:clear|sell|move|shift|dispose of|target(?:ing)?|stock of)\s*(?:about\s*)?(\d+)\s*(?:units?|products?|items?)?",
            req.message,
            re.IGNORECASE,
        )
        if quantity_match:
            target_units = int(quantity_match.group(1))

    deadline_days = req.deadline_days
    deadline_match = re.search(
        r"(?:within|in|over|next)\s+(\d+)\s+days?",
        req.message,
        re.IGNORECASE,
    )
    if deadline_match:
        deadline_days = max(1, min(365, int(deadline_match.group(1))))

    context["request"]["deadline_days"] = deadline_days
    context["request"]["target_units"] = target_units
    resolved_objective = (
        "clearance"
        if any(
            word in req.message.lower()
            for word in ("as soon as possible", "fastest", "clear quickly", "minimum profit")
        )
        else req.objective
    )
    context["request"]["objective"] = resolved_objective

    # If a SKU is found, add its forecast and real optimizer result.
    if selected_sku:
        product = store.product(selected_sku)

        if not product:
            raise HTTPException(
                status_code=404,
                detail="SKU not found. Choose a SKU from /api/products.",
            )

        brand = store.brand(product.brand_id)

        if not brand:
            raise HTTPException(
                status_code=422,
                detail="Brand details are missing for this SKU.",
            )

        stock = store.stock(selected_sku)
        last30 = store.last30_units(selected_sku)

        baseline_daily = max(last30 / 30, 0.0)
        forecast_summary = None
        forecast_status = "historical_fallback"
        forecast_horizon = min(deadline_days, 90)

        try:
            forecast_summary = forecast_sku(
                store.sales(),
                selected_sku,
                forecast_horizon,
            )

            baseline_daily = max(
                0.0,
                float(
                    forecast_summary[
                        "average_forecast_units_per_day"
                    ]
                ),
            )
            forecast_status = "forecast_model"

        except (ValueError, KeyError, TypeError) as exc:
            forecast_summary = {
                "status": "unavailable",
                "reason": str(exc),
                "fallback": "recent_30_day_sales_rate",
            }

        try:
            full_result = optimize_product(
                product,
                brand,
                stock,
                baseline_daily,
                deadline_days,
                resolved_objective,
                target_units=target_units,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        recommendation = full_result.get("recommendation") or {}

        context["selected_product"] = {
            "sku": product.sku,
            "product_name": product.product_name,
            "brand": brand.name,
            "category": product.category,
            "cost_price": product.cost_price,
            "selling_price": product.selling_price,
            "current_stock": stock,
            "target_units": min(stock, target_units) if target_units is not None else stock,
            "units_sold_last_30_days": last30,
        }

        context["forecast_result"] = {
            "source": forecast_status,
            "horizon_days": (
                forecast_horizon
                if forecast_status == "forecast_model"
                else None
            ),
            "forecast_units_total": (
                forecast_summary.get("forecast_units_total")
                if forecast_status == "forecast_model"
                else None
            ),
            "average_forecast_units_per_day": round(
                baseline_daily, 3
            ),
            "selected_forecast_method": (
                forecast_summary.get("selected_forecast_method")
                if forecast_status == "forecast_model"
                else None
            ),
            "evaluation": (
                forecast_summary.get("evaluation")
                if forecast_status == "forecast_model"
                else None
            ),
            "caveats": (
                forecast_summary.get("caveats", [])
                if forecast_status == "forecast_model"
                else [forecast_summary.get("reason", "Forecast unavailable.")]
            ),
        }

        context["optimization_result"] = {
            "sku": full_result.get("sku"),
            "product_name": full_result.get("product_name"),
            "brand": full_result.get("brand"),
            "current_stock": full_result.get("current_stock"),
            "target_units": full_result.get("target_units"),
            "deadline_days": full_result.get("deadline_days"),
            "objective": full_result.get("objective"),
            "minimum_margin_percent": full_result.get(
                "minimum_margin_percent"
            ),
            "scenarios_evaluated": full_result.get(
                "scenarios_evaluated"
            ),
            "feasible_scenarios_count": full_result.get(
                "feasible_scenarios_count"
            ),
            "has_feasible_recommendation": full_result.get(
                "has_feasible_recommendation"
            ),
            "recommendation": {
                key: recommendation.get(key)
                for key in (
                    "promotion_type",
                    "label",
                    "discount_percent",
                    "effective_unit_price",
                    "expected_units_sold",
                    "expected_revenue",
                    "cost_of_goods_sold",
                    "estimated_promotion_cost",
                    "estimated_net_profit",
                    "estimated_margin_percent",
                    "estimated_daily_units",
                    "estimated_clearance_days",
                    "expected_stock_remaining",
                    "meets_deadline",
                    "meets_minimum_margin",
                    "eligible",
                    "feasible",
                    "scenario_warning",
                    "financial_note",
                    "estimate_note",
                )
                if key in recommendation
            },
            "alternative_scenarios": [
                {
                    key: scenario.get(key)
                    for key in (
                        "label", "promotion_type", "discount_percent",
                        "effective_unit_price", "expected_units_sold",
                        "estimated_net_profit", "estimated_margin_percent",
                        "estimated_clearance_days", "eligible", "feasible",
                        "meets_minimum_margin", "meets_deadline", "estimate_note"
                    )
                    if key in scenario
                }
                for scenario in full_result.get("all_scenarios", [])[:6]
            ],
            "warning": full_result.get("warning"),
            "selection_reason": full_result.get("selection_reason"),
            "methodology_note": full_result.get("methodology_note"),
            "data_basis": "synthetic demo Excel data",
        }

    # 5. Send the question and verified data to the existing AI service.
    return grounded_answer(req.message, context)
