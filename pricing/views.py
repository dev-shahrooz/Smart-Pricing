from collections import defaultdict
from typing import List

from django.http import HttpResponse
from django.shortcuts import render

from .bom_loader import BomCsvError, load_bom_from_csv
from .domain_models import (
    BomItem,
    FinanceParams,
    InventoryParams,
    LogisticsParams,
    ManufacturingParams,
    MarketParams,
)
from .pricing_engine import compute_cost_breakdown, compute_recommended_price
from .state import BOM_STORE


def home(request):
    return HttpResponse('Smart Pricing Engine')


def bom_upload_view(request):
    context: dict[str, object] = {}

    if request.method == "POST":
        bom_file = request.FILES.get("bom_file")
        if not bom_file:
            context["error"] = "Please select a BOM CSV file to upload."
        else:
            try:
                bom_items: List[BomItem] = load_bom_from_csv(bom_file)
            except BomCsvError as exc:
                context["error"] = str(exc)
            else:
                BOM_STORE.clear()
                grouped_items: dict[str, list[BomItem]] = defaultdict(list)
                for item in bom_items:
                    grouped_items[item.product_code].append(item)

                BOM_STORE.update(grouped_items)
                context["product_codes"] = sorted(grouped_items.keys())

    return render(request, "pricing/bom_upload.html", context)


def pricing_form_view(request):
    context: dict[str, object] = {
        "product_codes": sorted(BOM_STORE.keys()),
        "form_values": {},
    }

    def _to_int(value: str | None, default: int = 0) -> int:
        try:
            return int(value) if value is not None and value != "" else default
        except ValueError:
            return default

    def _to_float(value: str | None, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None and value != "" else default
        except ValueError:
            return default

    if request.method == "POST":
        product_code = request.POST.get("product_code") or ""

        manufacturing_params = ManufacturingParams(
            smd_cost_per_component=_to_int(request.POST.get("smd_cost_per_component")),
            tht_cost_per_component=_to_int(request.POST.get("tht_cost_per_component")),
            assembly_time_min=_to_float(request.POST.get("assembly_time_min")),
            qc_test_time_min=_to_float(request.POST.get("qc_test_time_min")),
            worker_hour_cost=_to_int(request.POST.get("worker_hour_cost")),
        )

        logistics_params = LogisticsParams(
            shipping_cost_usd=_to_float(request.POST.get("shipping_cost_usd")),
            custom_clearance_irr=_to_int(request.POST.get("custom_clearance_irr")),
            duty_percent=_to_float(request.POST.get("duty_percent")),
            exchange_rate_buy=_to_int(request.POST.get("exchange_rate_buy")),
        )

        inventory_params = InventoryParams(
            inventory_days=_to_int(request.POST.get("inventory_days")),
            capital_cost_rate=_to_float(request.POST.get("capital_cost_rate")),
        )

        market_params = MarketParams(
            competitor_price_avg=_to_int(request.POST.get("competitor_price_avg")),
            elasticity=_to_float(request.POST.get("elasticity")),
        )

        finance_params = FinanceParams(
            exchange_rate_now=_to_int(request.POST.get("exchange_rate_now")),
            target_margin_percent=_to_float(request.POST.get("target_margin_percent")),
        )

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

        context.update(
            {
                "selected_product_code": product_code,
                "cost_breakdown": cost_breakdown,
                "total_cost": cost_breakdown.total_cost_irr,
                "recommended_price": recommended_price,
                "form_values": request.POST,
            }
        )

    return render(request, "pricing/pricing_form.html", context)
