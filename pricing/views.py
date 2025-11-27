from collections import defaultdict
from typing import List

from django.http import HttpResponse
from django.shortcuts import render

from .bom_loader import BomCsvError, load_bom_from_csv
from .domain_models import BomItem
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
