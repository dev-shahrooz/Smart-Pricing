"""Utilities for loading BOM data from CSV files."""
from __future__ import annotations

import csv
import io
from typing import Iterable, List

from .domain_models import BomItem


class BomCsvError(Exception):
    """Raised when a BOM CSV file cannot be parsed."""


REQUIRED_COLUMNS = {"product_code", "part_name", "quantity", "unit_price_usd"}


def _normalize_file(file_obj: Iterable[bytes] | Iterable[str]) -> io.StringIO:
    """Return a text stream for the uploaded file."""
    if hasattr(file_obj, "read"):
        content = file_obj.read()
    else:
        content = b"".join(file_obj)  # type: ignore[arg-type]

    if isinstance(content, bytes):
        text = content.decode("utf-8")
    else:
        text = content

    return io.StringIO(text)


def load_bom_from_csv(file_obj: Iterable[bytes] | Iterable[str]) -> List[BomItem]:
    """Parse BOM items from a CSV upload.

    The CSV file must include headers: ``product_code``, ``part_name``,
    ``quantity``, and ``unit_price_usd``.
    """

    text_stream = _normalize_file(file_obj)
    reader = csv.DictReader(text_stream)

    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset({name.strip() for name in reader.fieldnames}):
        raise BomCsvError(
            "CSV is missing required columns: product_code, part_name, quantity, unit_price_usd"
        )

    bom_items: list[BomItem] = []
    for line_number, row in enumerate(reader, start=2):
        try:
            product_code = (row.get("product_code") or "").strip()
            part_name = (row.get("part_name") or "").strip()
            quantity_raw = row.get("quantity")
            unit_price_raw = row.get("unit_price_usd")
        except AttributeError as exc:  # pragma: no cover - defensive
            raise BomCsvError("Invalid CSV row format") from exc

        if not product_code or not part_name:
            raise BomCsvError(f"Row {line_number}: product_code and part_name are required")

        try:
            quantity = int(quantity_raw) if quantity_raw is not None else 0
        except ValueError as exc:
            raise BomCsvError(f"Row {line_number}: quantity must be an integer") from exc

        try:
            unit_price_usd = float(unit_price_raw) if unit_price_raw is not None else 0.0
        except ValueError as exc:
            raise BomCsvError(f"Row {line_number}: unit_price_usd must be a number") from exc

        bom_items.append(
            BomItem(
                product_code=product_code,
                part_name=part_name,
                quantity=quantity,
                unit_price_usd=unit_price_usd,
            )
        )

    if not bom_items:
        raise BomCsvError("CSV contains no BOM rows")

    return bom_items


__all__ = ["BomCsvError", "load_bom_from_csv"]
