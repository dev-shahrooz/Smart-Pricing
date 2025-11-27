"""Simple in-memory storage for BOM data."""
from __future__ import annotations

from typing import Dict, List

from .domain_models import BomItem

# Maps product codes to lists of BOM items
BOM_STORE: Dict[str, List[BomItem]] = {}


def set_bom_store(mapping: Dict[str, List[BomItem]]) -> None:
    """Replace the in-memory BOM store with the given mapping."""
    BOM_STORE.clear()
    BOM_STORE.update(mapping)


def get_bom_for_product(product_code: str) -> list[BomItem] | None:
    """Return BOM items for a specific product code, or None if missing."""
    return BOM_STORE.get(product_code)


def get_all_product_codes() -> list[str]:
    """Return all known product codes, sorted."""
    return sorted(BOM_STORE.keys())
