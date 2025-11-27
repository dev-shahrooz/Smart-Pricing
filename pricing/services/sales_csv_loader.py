from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Dict, IO, List


@dataclass
class SalesRecord:
    month: str          # e.g. "2024-01"
    product_code: str
    price: int          # IRR
    units_sold: int     # units


class SalesCsvError(Exception):
    """Raised when the sales CSV file is invalid."""
    pass


def load_sales_from_csv(file_obj: IO) -> Dict[str, List[SalesRecord]]:
    """
    Parse a sales CSV and return a mapping:
    { product_code: [SalesRecord, ...], ... }

    Required columns:
    - month
    - product_code
    - price
    - units_sold
    """
    text = file_obj.read().decode("utf-8") if hasattr(file_obj, "read") else file_obj
    if isinstance(text, bytes):
        text = text.decode("utf-8")

    reader = csv.DictReader(text.splitlines())
    required_cols = {"month", "product_code", "price", "units_sold"}
    if not required_cols.issubset(reader.fieldnames or []):
        missing = required_cols - set(reader.fieldnames or [])
        raise SalesCsvError(f"Missing required columns in sales CSV: {', '.join(sorted(missing))}")

    mapping: Dict[str, List[SalesRecord]] = {}

    for row in reader:
        try:
            month = row["month"].strip()
            product_code = row["product_code"].strip()
            price = int(row["price"])
            units_sold = int(row["units_sold"])
        except (KeyError, ValueError) as exc:
            raise SalesCsvError(f"Invalid row in sales CSV: {row}") from exc

        if price < 0 or units_sold < 0:
            raise SalesCsvError(f"Negative values are not allowed in sales CSV: {row}")

        rec = SalesRecord(
            month=month,
            product_code=product_code,
            price=price,
            units_sold=units_sold,
        )
        mapping.setdefault(product_code, []).append(rec)

    return mapping
