from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from typing import IO, List


@dataclass
class FxHistoryPoint:
    date: dt.date
    rate: float  # IRR per USD


class FxCsvError(Exception):
    """Raised when the FX CSV file is invalid."""


    pass


def load_fx_history_from_csv(file_obj: IO) -> List[FxHistoryPoint]:
    """
    Parse a CSV file with historical FX rates.

    Expected columns:
      - date  (YYYY-MM-DD)
      - usd_irr  (numeric)

    Returns a list of FxHistoryPoint sorted by date ascending.
    """
    raw = file_obj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)

    reader = csv.DictReader(text.splitlines())
    required = {"date", "usd_irr"}
    if not required.issubset(set(reader.fieldnames or [])):
        missing = required - set(reader.fieldnames or [])
        raise FxCsvError(f"Missing required columns in FX CSV: {', '.join(sorted(missing))}")

    points: List[FxHistoryPoint] = []
    for row in reader:
        try:
            date_str = row["date"].strip()
            rate_str = row["usd_irr"].strip()
            date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
            rate = float(rate_str)
        except Exception as exc:  # ValueError, KeyError, etc.
            raise FxCsvError(f"Invalid FX row: {row}") from exc

        if rate <= 0:
            raise FxCsvError(f"FX rate must be positive: {row}")

        points.append(FxHistoryPoint(date=date, rate=rate))

    points.sort(key=lambda p: p.date)
    if len(points) < 5:
        raise FxCsvError("FX CSV must contain at least 5 data points.")
    return points
