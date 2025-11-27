from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

MODELS_DIR = Path(__file__).resolve().parent / "models"


@dataclass
class LinearTimeModel:
    slope: float
    intercept: float
    last_month: str

    def predict(self, month_numeric: float) -> float:
        return self.slope * month_numeric + self.intercept


def _require_columns(df: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "component"


def _period_to_numeric(period: pd.Period) -> float:
    timestamp = period.to_timestamp()
    return timestamp.timestamp()


def _fit_linear_model(months: pd.Series, prices: pd.Series) -> LinearTimeModel:
    month_numeric = months.apply(_period_to_numeric).to_numpy()
    price_values = prices.to_numpy()

    if len(month_numeric) == 1:
        slope = 0.0
        intercept = float(price_values[0])
    else:
        slope, intercept = np.polyfit(month_numeric, price_values, deg=1)

    return LinearTimeModel(slope=float(slope), intercept=float(intercept), last_month=str(months.iloc[-1]))


def train_from_csv(csv_path: str) -> None:
    """
    Train models per component and persist them to disk (pickle files under
    ``pricing/ml/models/``).
    """

    data = pd.read_csv(csv_path)
    _require_columns(data, {"date", "part_name", "unit_price_usd", "qty", "source"})
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "part_name", "unit_price_usd"])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for part_name, part_df in data.groupby("part_name"):
        monthly = (
            part_df.assign(month=part_df["date"].dt.to_period("M"))
            .groupby("month")["unit_price_usd"]
            .mean()
            .sort_index()
        )

        if monthly.empty:
            continue

        model = _fit_linear_model(monthly.index.to_series(), monthly.reset_index(drop=True))
        model_path = MODELS_DIR / f"{_slugify(part_name)}.pkl"
        with model_path.open("wb") as f:
            pickle.dump(model.__dict__, f)


def predict_next_month(part_name: str) -> float:
    """
    Load the trained model for the given part and return the predicted
    ``unit_price_usd`` for next month.
    """

    model_path = MODELS_DIR / f"{_slugify(part_name)}.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"No trained model found for part '{part_name}'")

    with model_path.open("rb") as f:
        raw_data: Dict[str, object] = pickle.load(f)

    model = LinearTimeModel(**raw_data)
    last_month = pd.Period(model.last_month)
    next_month = last_month + 1
    next_month_numeric = _period_to_numeric(next_month)
    return float(model.predict(next_month_numeric))
