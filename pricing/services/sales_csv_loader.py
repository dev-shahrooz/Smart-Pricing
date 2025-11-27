from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from typing import IO, Dict, List


class SalesCsvError(Exception):
    """Custom exception for sales CSV parsing errors."""


@dataclass
class SalesRecord:
    month: str  # YYYY-MM
    product_code: str
    price: int  # IRR
    units_sold: int


def _is_header_row(row: List[str]) -> bool:
    normalized = [value.strip().lower() for value in row]
    return normalized == ["month", "product_code", "price", "units_sold"]


def load_sales_from_csv(file_obj: IO) -> Dict[str, List[SalesRecord]]:
    """
    Parse a sales CSV file and return a dict mapping product_code to a list of
    SalesRecord objects.

    The expected CSV format is:
    month,product_code,price,units_sold
    2024-01,USB-CH32,420000,580
    """

    reader = csv.reader(file_obj)
    sales_by_product: Dict[str, List[SalesRecord]] = defaultdict(list)

    for index, row in enumerate(reader, start=1):
        if not row or all(cell.strip() == "" for cell in row):
            continue

        if index == 1 and _is_header_row(row):
            continue

        if len(row) != 4:
            raise SalesCsvError(f"Row {index} has {len(row)} columns; expected 4")

        month, product_code, price_str, units_sold_str = (cell.strip() for cell in row)

        if not month or not product_code:
            raise SalesCsvError(f"Row {index} is missing required fields")

        try:
            price = int(price_str)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise SalesCsvError(f"Row {index} has invalid price: {price_str}") from exc

        try:
            units_sold = int(units_sold_str)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise SalesCsvError(f"Row {index} has invalid units_sold: {units_sold_str}") from exc

        record = SalesRecord(
            month=month,
            product_code=product_code,
            price=price,
            units_sold=units_sold,
        )
        sales_by_product[product_code].append(record)

    return dict(sales_by_product)
