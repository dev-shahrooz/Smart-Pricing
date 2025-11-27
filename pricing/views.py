from collections import defaultdict
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
    MarketParams,
)
from .pricing_engine import (
    compute_cost_breakdown,
    compute_recommended_price,
    simulate_prices_for_exchange_rates,
)
from .state import BOM_STORE


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
                BOM_STORE.clear()
                grouped_items: dict[str, list[BomItem]] = defaultdict(list)
                for item in bom_items:
                    grouped_items[item.product_code].append(item)

                BOM_STORE.update(grouped_items)
                context["product_codes"] = sorted(grouped_items.keys())
                messages.success(request, "BOM uploaded successfully.")

    return render(request, "pricing/bom_upload.html", context)


def pricing_form_view(request):
    context: dict[str, object] = {
        "product_codes": sorted(BOM_STORE.keys()),
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

            market_params = MarketParams(
                competitor_price_avg=_require_int(
                    request.POST.get("competitor_price_avg"),
                    "Competitor price average",
                ),
                elasticity=_require_float(
                    request.POST.get("elasticity"), "Elasticity"
                ),
            )

            finance_params = FinanceParams(
                exchange_rate_now=_require_int(
                    request.POST.get("exchange_rate_now"), "Exchange rate now"
                ),
                target_margin_percent=_require_float(
                    request.POST.get("target_margin_percent"), "Target margin"
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
                    market=market_params,
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
        "product_codes": sorted(BOM_STORE.keys()),
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

            market_params = MarketParams(
                competitor_price_avg=_require_int(
                    request.POST.get("competitor_price_avg"),
                    "Competitor price average",
                ),
                elasticity=_require_float(
                    request.POST.get("elasticity"), "Elasticity"
                ),
            )

            finance_params = FinanceParams(
                exchange_rate_now=_require_int(
                    request.POST.get("exchange_rate_now"), "Exchange rate now"
                ),
                target_margin_percent=_require_float(
                    request.POST.get("target_margin_percent"), "Target margin"
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
                    market=market_params,
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
