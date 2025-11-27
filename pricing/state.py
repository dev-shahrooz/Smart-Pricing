"""Simple in-memory storage for BOM data."""
from __future__ import annotations

from typing import Dict, List

from .domain_models import BomItem

# Maps product codes to lists of BOM items
BOM_STORE: Dict[str, List[BomItem]] = {}
