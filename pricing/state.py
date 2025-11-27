"""Simple in-memory storage for BOM data."""
from __future__ import annotations

from typing import Dict, List

from .domain_models import BomItem

# Maps product codes to lists of BOM items
BOM_STORE: Dict[str, List[BomItem]] = {}


def set_bom_store(mapping: Dict[str, List[BomItem]]) -> None:
    """Replace the in-memory BOM store with the provided mapping."""

    BOM_STORE.clear()
    BOM_STORE.update(mapping)


def get_all_product_codes() -> list[str]:
    """Return all known product codes sorted alphabetically."""

    return sorted(BOM_STORE.keys())
