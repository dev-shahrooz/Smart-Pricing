from collections import defaultdict
import json
from typing import List

from django.contrib import messages
from django.shortcuts import redirect, render

from .bom_loader import BomCsvError, load_bom_from_csv
from .domain_models import (
    BomItem,
    FinanceParams,
    InventoryParams,
    LogisticsParams,
    ManufacturingParams,
)
from .ml.demand_elasticity import (
    ElasticityResult,
    compute_optimal_price,
    fit_elasticity_for_product,
)
from .ml.fx_forecast import FxForecastResult, forecast_fx
from .pricing_engine import (
    compute_cost_breakdown,
    compute_recommended_price,
    simulate_prices_for_exchange_rates,
)
from .services.fx_csv_loader import FxCsvError, load_fx_history_from_csv
from .services.sales_csv_loader import SalesCsvError, load_sales_from_csv
from .state import BOM_STORE, get_all_product_codes, get_bom_for_product, set_bom_store


def home(request):
    return redirect("pricing_form")


def bom_upload_view(request):
    context: dict[str, object] = {}

    if request.method == "POST":
        bom_file = request.FILES.get("bom_file")
        if not bom_file:
            messages.error(request, "Please select a BOM CSV file to upload.")
        elif not bom_file.name.lower().endswith(".csv"):
            messages.error(request, "The uploaded file must be a .csv file.")
        else:
            try:
                bom_items: List[BomItem] = load_bom_from_csv(bom_file)
            except BomCsvError as exc:
                messages.error(request, str(exc))
            else:
                grouped_items: dict[str, list[BomItem]] = defaultdict(list)
                for item in bom_items:
                    grouped_items[item.product_code].append(item)

                set_bom_store(grouped_items)
                context["product_codes"] = get_all_product_codes()
                messages.success(request, "BOM uploaded successfully.")

    return render(request, "pricing/bom_upload.html", context)


def pricing_form_view(request):
    context: dict[str, object] = {
        "product_codes": get_all_product_codes(),
        "form_values": {},
    }

    def _require_int(value: str | None, field_name: str) -> int:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a whole number.") from exc

    def _require_float(value: str | None, field_name: str) -> float:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a number.") from exc

    if request.method == "POST":
        product_code = request.POST.get("product_code") or ""

        try:
            manufacturing_params = ManufacturingParams(
                smd_cost_per_component=_require_int(
                    request.POST.get("smd_cost_per_component"),
                    "SMD cost per component",
                ),
                tht_cost_per_component=_require_int(
                    request.POST.get("tht_cost_per_component"),
                    "THT cost per component",
                ),
                assembly_time_min=_require_float(
                    request.POST.get("assembly_time_min"), "Assembly time"
                ),
                qc_test_time_min=_require_float(
                    request.POST.get("qc_test_time_min"), "QC/Test time"
                ),
                worker_hour_cost=_require_int(
                    request.POST.get("worker_hour_cost"), "Worker hour cost"
                ),
            )

            logistics_params = LogisticsParams(
                shipping_cost_usd=_require_float(
                    request.POST.get("shipping_cost_usd"), "Shipping cost"
                ),
                custom_clearance_irr=_require_int(
                    request.POST.get("custom_clearance_irr"), "Custom clearance"
                ),
                duty_percent=_require_float(
                    request.POST.get("duty_percent"), "Duty percent"
                ),
                exchange_rate_buy=_require_int(
                    request.POST.get("exchange_rate_buy"), "Exchange rate buy"
                ),
            )

            inventory_params = InventoryParams(
                inventory_days=_require_int(
                    request.POST.get("inventory_days"), "Inventory days"
                ),
                capital_cost_rate=_require_float(
                    request.POST.get("capital_cost_rate"), "Capital cost rate"
                ),
            )

            finance_params = FinanceParams(
                exchange_rate_now=_require_int(
                    request.POST.get("exchange_rate_now"), "Exchange rate now"
                ),
                target_margin_percent=_require_float(
                    request.POST.get("target_margin_percent"), "Target margin"
                ),
                competitor_price_avg=_require_int(
                    request.POST.get("competitor_price_avg"),
                    "Competitor price average",
                ),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            if not product_code:
                messages.error(request, "Please select a product code.")
            elif product_code not in BOM_STORE:
                messages.error(
                    request,
                    "The selected product code is missing. Please upload the BOM first.",
                )
            else:
                bom_items = BOM_STORE.get(product_code, [])

                cost_breakdown = compute_cost_breakdown(
                    bom_items=bom_items,
                    manufacturing=manufacturing_params,
                    logistics=logistics_params,
                    inventory=inventory_params,
                )

                recommended_price = compute_recommended_price(
                    cost_breakdown=cost_breakdown,
                    finance=finance_params,
                )

                messages.success(request, "Price calculated successfully.")

                context.update(
                    {
                        "selected_product_code": product_code,
                        "cost_breakdown": cost_breakdown,
                        "total_cost": cost_breakdown.total_cost_irr,
                        "recommended_price": recommended_price["final_suggested_price"],
                        "recommended_price_details": recommended_price,
                        "form_values": request.POST,
                    }
                )

        context.setdefault("form_values", request.POST)

    return render(request, "pricing/pricing_form.html", context)


def scenario_view(request):
    context: dict[str, object] = {
        "product_codes": get_all_product_codes(),
        "form_values": {},
        "scenario_results": [],
        "exchange_rates_raw": "",
    }

    def _require_int(value: str | None, field_name: str) -> int:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a whole number.") from exc

    def _require_float(value: str | None, field_name: str) -> float:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a number.") from exc

    def _parse_exchange_rates(raw_value: str | None) -> list[int]:
        if raw_value is None or raw_value.strip() == "":
            raise ValueError("Exchange rates are required.")

        rates: list[int] = []
        for part in raw_value.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                rates.append(int(part))
            except ValueError as exc:  # noqa: PERF203
                raise ValueError(
                    "Exchange rates must be integers separated by commas."
                ) from exc
        if not rates:
            raise ValueError("Please provide at least one exchange rate.")
        return rates

    if request.method == "POST":
        product_code = request.POST.get("product_code") or ""
        exchange_rates_raw = request.POST.get("exchange_rates_raw") or ""

        try:
            manufacturing_params = ManufacturingParams(
                smd_cost_per_component=_require_int(
                    request.POST.get("smd_cost_per_component"),
                    "SMD cost per component",
                ),
                tht_cost_per_component=_require_int(
                    request.POST.get("tht_cost_per_component"),
                    "THT cost per component",
                ),
                assembly_time_min=_require_float(
                    request.POST.get("assembly_time_min"), "Assembly time"
                ),
                qc_test_time_min=_require_float(
                    request.POST.get("qc_test_time_min"), "QC/Test time"
                ),
                worker_hour_cost=_require_int(
                    request.POST.get("worker_hour_cost"), "Worker hour cost"
                ),
            )

            logistics_params = LogisticsParams(
                shipping_cost_usd=_require_float(
                    request.POST.get("shipping_cost_usd"), "Shipping cost"
                ),
                custom_clearance_irr=_require_int(
                    request.POST.get("custom_clearance_irr"), "Custom clearance"
                ),
                duty_percent=_require_float(
                    request.POST.get("duty_percent"), "Duty percent"
                ),
                exchange_rate_buy=_require_int(
                    request.POST.get("exchange_rate_buy"), "Exchange rate buy"
                ),
            )

            inventory_params = InventoryParams(
                inventory_days=_require_int(
                    request.POST.get("inventory_days"), "Inventory days"
                ),
                capital_cost_rate=_require_float(
                    request.POST.get("capital_cost_rate"), "Capital cost rate"
                ),
            )

            finance_params = FinanceParams(
                exchange_rate_now=_require_int(
                    request.POST.get("exchange_rate_now"), "Exchange rate now"
                ),
                target_margin_percent=_require_float(
                    request.POST.get("target_margin_percent"), "Target margin"
                ),
                competitor_price_avg=_require_int(
                    request.POST.get("competitor_price_avg"),
                    "Competitor price average",
                ),
            )

            exchange_rates = _parse_exchange_rates(exchange_rates_raw)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            if not product_code:
                messages.error(request, "Please select a product code.")
            elif product_code not in BOM_STORE:
                messages.error(
                    request,
                    "The selected product code is missing. Please upload the BOM first.",
                )
            else:
                bom_items = BOM_STORE.get(product_code, [])

                scenario_results = simulate_prices_for_exchange_rates(
                    bom_items=bom_items,
                    exchange_rates=exchange_rates,
                    manufacturing=manufacturing_params,
                    logistics=logistics_params,
                    inventory=inventory_params,
                    finance=finance_params,
                )

                messages.success(request, "Scenario simulation completed.")

                context.update(
                    {
                        "selected_product_code": product_code,
                        "scenario_results": scenario_results,
                        "form_values": request.POST,
                        "exchange_rates_raw": exchange_rates_raw,
                    }
                )

        context.setdefault("form_values", request.POST)

    return render(request, "pricing/scenario.html", context)


def ai_insights_view(request):
    """
    AI Pricing Insights:
    - Select product
    - Optional: upload sales CSV
    - Enter cost/finance params
    - See cost-plus price, ML optimal price (if sales provided), and profit curve.
    """
    context: dict[str, object] = {
        "product_codes": get_all_product_codes(),
        "form_values": {"use_regularization": "on"},
        "elasticity_result": None,
        "cost_breakdown": None,
        "recommended_price": None,
        "final_suggested_price": None,
        "price_grid": [],
        "profit_grid": [],
        "fx_forecast": None,
        "future_price_points": [],
        "fx_chart_json": "{}",
    }

    def _require_int(value: str | None, field_name: str) -> int:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        return int(value)

    def _require_float(value: str | None, field_name: str) -> float:
        if value is None or value == "":
            raise ValueError(f"{field_name} is required.")
        return float(value)

    if request.method == "POST":
        product_code = request.POST.get("product_code") or ""
        context["form_values"] = request.POST.copy()
        context["selected_product_code"] = product_code

        use_regularization = request.POST.get("use_regularization") == "on"
        regularization_strength = 0.1
        elasticity_bounds = (-3.0, -0.3)
        context["form_values"]["use_regularization"] = "on" if use_regularization else ""

        if not product_code:
            messages.error(request, "Please select a product code.")
        else:
            bom_items = get_bom_for_product(product_code)
            if not bom_items:
                messages.error(
                    request,
                    "No BOM found for this product. Please upload a BOM first.",
                )
            else:
                try:
                    manufacturing_params = ManufacturingParams(
                        smd_cost_per_component=_require_int(
                            request.POST.get("smd_cost_per_component"),
                            "SMD cost per component",
                        ),
                        tht_cost_per_component=_require_int(
                            request.POST.get("tht_cost_per_component"),
                            "THT cost per component",
                        ),
                        assembly_time_min=_require_float(
                            request.POST.get("assembly_time_min"), "Assembly time"
                        ),
                        qc_test_time_min=_require_float(
                            request.POST.get("qc_test_time_min"), "QC test time"
                        ),
                        worker_hour_cost=_require_int(
                            request.POST.get("worker_hour_cost"), "Worker hour cost"
                        ),
                    )

                    logistics_params = LogisticsParams(
                        shipping_cost_usd=_require_float(
                            request.POST.get("shipping_cost_usd"),
                            "Shipping cost (USD)",
                        ),
                        custom_clearance_irr=_require_int(
                            request.POST.get("custom_clearance_irr"),
                            "Custom clearance (IRR)",
                        ),
                        duty_percent=_require_float(
                            request.POST.get("duty_percent"),
                            "Duty percent",
                        ),
                        exchange_rate_buy=_require_int(
                            request.POST.get("exchange_rate_buy"),
                            "Exchange rate buy",
                        ),
                    )

                    inventory_params = InventoryParams(
                        inventory_days=_require_int(
                            request.POST.get("inventory_days"), "Inventory days"
                        ),
                        capital_cost_rate=_require_float(
                            request.POST.get("capital_cost_rate"),
                            "Capital cost rate",
                        ),
                    )

                    finance_params = FinanceParams(
                        exchange_rate_now=_require_int(
                            request.POST.get("exchange_rate_now"),
                            "Exchange rate now",
                        ),
                        target_margin_percent=_require_float(
                            request.POST.get("target_margin_percent"),
                            "Target margin percent",
                        ),
                        competitor_price_avg=_require_int(
                            request.POST.get("competitor_price_avg") or "0",
                            "Competitor price avg",
                        ),
                    )

                    fx_horizon_str = request.POST.get("fx_forecast_days") or ""
                    try:
                        fx_horizon_days = int(fx_horizon_str) if fx_horizon_str else 0
                    except ValueError:
                        fx_horizon_days = 0
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    # Base cost and cost-plus price
                    cost_breakdown = compute_cost_breakdown(
                        bom_items=bom_items,
                        manufacturing=manufacturing_params,
                        logistics=logistics_params,
                        inventory=inventory_params,
                    )
                    recommended_details = compute_recommended_price(
                        cost_breakdown=cost_breakdown,
                        finance=finance_params,
                    )

                    elasticity_result: ElasticityResult | None = None
                    fx_forecast_result: FxForecastResult | None = None
                    future_price_points: list[dict] = []

                    # Optional: sales CSV for ML
                    sales_file = request.FILES.get("sales_file")
                    if sales_file:
                        try:
                            sales_mapping = load_sales_from_csv(sales_file)
                            records = sales_mapping.get(product_code, [])
                            if records:
                                model = fit_elasticity_for_product(
                                    records,
                                    regularization_strength=regularization_strength
                                    if use_regularization
                                    else 0.0,
                                    elasticity_bounds=elasticity_bounds,
                                )
                                elasticity_result = compute_optimal_price(
                                    model,
                                    cost_per_unit=cost_breakdown.total_cost_irr,
                                )
                            else:
                                messages.warning(
                                    request,
                                    "No sales records found for this product in the CSV.",
                                )
                        except SalesCsvError as exc:
                            messages.error(request, f"Sales CSV error: {exc}")
                        except ValueError as exc:
                            messages.error(request, f"Could not fit elasticity: {exc}")

                    base_recommended_price = recommended_details.get(
                        "final_suggested_price", 0
                    )
                    final_price = base_recommended_price
                    if elasticity_result is not None:
                        if elasticity_result.all_negative:
                            messages.warning(
                                request,
                                "All candidate prices in the sales history are below unit cost; "
                                "no profitable price range was found.",
                            )
                            final_price = base_recommended_price
                        else:
                            # Blend cost-plus and ML price 50/50 as a simple compromise
                            final_price = (
                                base_recommended_price + elasticity_result.optimal_price
                            ) / 2

                    fx_file = request.FILES.get("fx_file")
                    fx_chart_json = "{}"
                    if fx_file and fx_horizon_days > 0:
                        try:
                            fx_points = load_fx_history_from_csv(fx_file)
                            fx_forecast_result = forecast_fx(
                                fx_points, horizon_days=fx_horizon_days
                            )

                            for date, rate, low, high in zip(
                                fx_forecast_result.forecast_dates,
                                fx_forecast_result.forecast_rates,
                                fx_forecast_result.forecast_low,
                                fx_forecast_result.forecast_high,
                            ):
                                logistics_future = LogisticsParams(
                                    shipping_cost_usd=logistics_params.shipping_cost_usd,
                                    custom_clearance_irr=logistics_params.custom_clearance_irr,
                                    duty_percent=logistics_params.duty_percent,
                                    exchange_rate_buy=int(rate),
                                )
                                finance_future = FinanceParams(
                                    exchange_rate_now=int(rate),
                                    target_margin_percent=finance_params.target_margin_percent,
                                    competitor_price_avg=finance_params.competitor_price_avg,
                                )

                                cb_future = compute_cost_breakdown(
                                    bom_items=bom_items,
                                    manufacturing=manufacturing_params,
                                    logistics=logistics_future,
                                    inventory=inventory_params,
                                )
                                base_price_future_details = compute_recommended_price(
                                    cost_breakdown=cb_future,
                                    finance=finance_future,
                                )
                                base_price_future = base_price_future_details.get(
                                    "final_suggested_price", 0
                                )

                                if elasticity_result is not None:
                                    final_future = (
                                        base_price_future + elasticity_result.optimal_price
                                    ) / 2.0
                                else:
                                    final_future = base_price_future

                                future_price_points.append(
                                    {
                                        "date": date,
                                        "fx_rate": rate,
                                        "fx_low": low,
                                        "fx_high": high,
                                        "base_price": base_price_future,
                                        "final_price": final_future,
                                        "total_cost": cb_future.total_cost_irr,
                                    }
                                )

                            fx_chart_json = json.dumps(
                                {
                                    "dates": [d.isoformat() for d in fx_forecast_result.forecast_dates],
                                    "rates": fx_forecast_result.forecast_rates,
                                    "prices": [p["final_price"] for p in future_price_points],
                                }
                            )
                        except FxCsvError as exc:
                            messages.error(request, f"FX CSV error: {exc}")
                        except ValueError as exc:
                            messages.error(request, f"Could not forecast FX: {exc}")

                    context.update(
                        {
                            "cost_breakdown": cost_breakdown,
                            "recommended_price": recommended_details.get(
                                "cost_plus_price", base_recommended_price
                            ),
                            "final_suggested_price": final_price,
                            "elasticity_result": elasticity_result,
                            "fx_forecast": fx_forecast_result,
                            "future_price_points": future_price_points,
                            "fx_chart_json": fx_chart_json,
                        }
                    )

                    if elasticity_result is not None:
                        context["price_grid"] = elasticity_result.price_grid
                        context["profit_grid"] = elasticity_result.profit_grid

                    messages.success(request, "AI pricing insights computed.")

    return render(request, "pricing/ai_insights.html", context)
