from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from pricing.services.sales_csv_loader import SalesRecord


@dataclass
class ElasticityModel:
    product_code: str
    a: float  # intercept in log-log space
    b: float  # slope = elasticity
    r2: float
    avg_price: float


@dataclass
class ElasticityResult:
    product_code: str
    elasticity: float
    optimal_price: float
    predicted_units_at_optimal: float
    max_profit: float
    price_grid: list[float]
    profit_grid: list[float]


def fit_elasticity_for_product(records: List[SalesRecord]) -> ElasticityModel:
    """Fit log(Q) = a + b * log(P) using simple linear regression."""
    xs: List[float] = []
    ys: List[float] = []

    for rec in records:
        if rec.price <= 0 or rec.units_sold <= 0:
            continue
        xs.append(math.log(rec.price))
        ys.append(math.log(rec.units_sold))

    if len(xs) < 3:
        raise ValueError("Not enough valid sales points to fit elasticity (need >= 3).")

    X = np.array(xs)
    Y = np.array(ys)

    n = len(X)
    x_mean = X.mean()
    y_mean = Y.mean()
    ss_xy = float(((X - x_mean) * (Y - y_mean)).sum())
    ss_xx = float(((X - x_mean) ** 2).sum())

    if ss_xx == 0:
        raise ValueError("Cannot fit elasticity model (all prices identical).")

    b = ss_xy / ss_xx
    a = y_mean - b * x_mean

    # R^2
    y_pred = a + b * X
    ss_tot = float(((Y - y_mean) ** 2).sum())
    ss_res = float(((Y - y_pred) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    avg_price = float(np.exp(X).mean())

    return ElasticityModel(
        product_code=records[0].product_code,
        a=a,
        b=b,
        r2=r2,
        avg_price=avg_price,
    )


def compute_optimal_price(
    model: ElasticityModel,
    cost_per_unit: float,
    num_points: int = 50,
) -> ElasticityResult:
    """
    Search for the profit-maximizing price in a grid from 80% to 150% of avg price.
    """
    p_min = 0.8 * model.avg_price
    p_max = 1.5 * model.avg_price
    price_grid = np.linspace(p_min, p_max, num_points)

    profits: List[float] = []
    units_list: List[float] = []

    for p in price_grid:
        log_q = model.a + model.b * math.log(p)
        q = math.exp(log_q)
        profit = (p - cost_per_unit) * q
        units_list.append(q)
        profits.append(profit)

    max_idx = int(np.argmax(profits))
    optimal_price = float(price_grid[max_idx])
    max_profit = float(profits[max_idx])
    predicted_units = float(units_list[max_idx])

    return ElasticityResult(
        product_code=model.product_code,
        elasticity=model.b,
        optimal_price=optimal_price,
        predicted_units_at_optimal=predicted_units,
        max_profit=max_profit,
        price_grid=[float(p) for p in price_grid],
        profit_grid=[float(v) for v in profits],
    )


def train_elasticity_from_mapping(
    sales_mapping: Dict[str, List[SalesRecord]],
    cost_per_unit: float,
) -> Dict[str, ElasticityResult]:
    """Fit elasticity for each product_code and return a mapping of results."""
    results: Dict[str, ElasticityResult] = {}
    for code, recs in sales_mapping.items():
        try:
            model = fit_elasticity_for_product(recs)
            result = compute_optimal_price(model, cost_per_unit=cost_per_unit)
        except Exception:
            continue
        results[code] = result
    return results
