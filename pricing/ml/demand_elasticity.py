from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

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
    elasticity_ci: Tuple[float, float] | None = None
    optimal_price_ci: Tuple[float, float] | None = None
    confidence_level: str | None = None
    regularized: bool = False
    regularization_strength: float = 0.0
    elasticity_bounds: Tuple[float, float] | None = None
    cost_factors: list[float] | None = None
    sensitivity_matrix: list[list[float]] | None = None
    all_negative: bool = False


def _fit_log_log_ridge(
    records: List[SalesRecord],
    regularization_strength: float = 0.0,
) -> Tuple[float, float, float, float]:
    """
    Fit log(Q) = a + b*log(P) using ridge-regularized linear regression.

    Returns:
        a, b, r2, stderr_b
    """
    xs: List[float] = []
    ys: List[float] = []

    for rec in records:
        if rec.price <= 0 or rec.units_sold <= 0:
            continue
        xs.append(math.log(rec.price))
        ys.append(math.log(rec.units_sold))

    if len(xs) < 3:
        raise ValueError("Not enough valid sales points to fit elasticity (need >= 3).")

    X = np.column_stack([np.ones(len(xs)), np.array(xs)])
    y = np.array(ys)

    # Ridge: (X^T X + λI)^{-1} X^T y
    lam = float(regularization_strength)
    I = np.eye(X.shape[1])
    XtX = X.T @ X
    XtX_reg = XtX + lam * I
    coeff = np.linalg.inv(XtX_reg) @ X.T @ y

    a = float(coeff[0])
    b = float(coeff[1])

    # R^2
    y_pred = X @ coeff
    y_mean = float(y.mean())
    ss_tot = float(((y - y_mean) ** 2).sum())
    ss_res = float(((y - y_pred) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Estimate stderr of slope b (approximate)
    dof = max(len(y) - 2, 1)
    sigma2 = ss_res / dof if dof > 0 else 0.0
    cov = sigma2 * np.linalg.inv(XtX_reg)
    stderr_b = float(math.sqrt(max(cov[1, 1], 0.0)))

    return a, b, r2, stderr_b


def fit_elasticity_for_product(
    records: List[SalesRecord],
    regularization_strength: float = 0.1,
    elasticity_bounds: Tuple[float, float] = (-3.0, -0.3),
) -> ElasticityModel:
    """Fit log-log elasticity model for one product with optional ridge regularization."""
    a, b_raw, r2, stderr_b = _fit_log_log_ridge(
        records,
        regularization_strength=regularization_strength,
    )

    # Clamp elasticity into reasonable bounds
    b_clamped = float(np.clip(b_raw, elasticity_bounds[0], elasticity_bounds[1]))

    avg_price = float(
        np.mean([rec.price for rec in records if rec.price > 0])
    )

    model = ElasticityModel(
        product_code=records[0].product_code,
        a=a,
        b=b_clamped,
        r2=r2,
        avg_price=avg_price,
    )
    # Attach extra info on model for later CI:
    model._stderr_b = stderr_b  # type: ignore[attr-defined]
    model._b_raw = b_raw  # type: ignore[attr-defined]
    model._regularization_strength = regularization_strength  # type: ignore[attr-defined]
    model._elasticity_bounds = elasticity_bounds  # type: ignore[attr-defined]
    return model


def compute_optimal_price(
    model: ElasticityModel,
    cost_per_unit: float,
    num_points: int = 50,
) -> ElasticityResult:
    """
    Search for the profit-maximizing price in a grid from 80% to 150% of avg price.
    Also compute confidence intervals and a simple price–cost sensitivity surface.
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
    all_negative = max_profit < 0

    # --- Elasticity CI (approximate 95%) ---
    stderr_b = getattr(model, "_stderr_b", 0.0)
    b_raw = getattr(model, "_b_raw", model.b)
    z = 1.96  # approx for 95% CI
    b_low = b_raw - z * stderr_b
    b_high = b_raw + z * stderr_b
    elasticity_ci = (float(b_low), float(b_high))

    # --- Price CI: region where profit >= 90% of max Profit ---
    threshold = max_profit * 0.9
    candidate_prices = [
        float(p)
        for p, prof in zip(price_grid, profits)
        if prof >= threshold
    ]
    if candidate_prices:
        price_ci = (min(candidate_prices), max(candidate_prices))
    else:
        price_ci = (optimal_price, optimal_price)

    # --- Confidence level heuristic ---
    span = price_ci[1] - price_ci[0]
    rel_span = span / optimal_price if optimal_price > 0 else 1.0
    if rel_span < 0.05:
        confidence = "high"
    elif rel_span < 0.15:
        confidence = "medium"
    else:
        confidence = "low"

    # --- Price sensitivity surface over cost factors ---
    cost_factors = [0.9, 1.0, 1.1, 1.2]
    sensitivity_matrix: List[List[float]] = []
    for f in cost_factors:
        row: List[float] = []
        effective_cost = cost_per_unit * f
        for p in price_grid:
            log_q = model.a + model.b * math.log(p)
            q = math.exp(log_q)
            prof = (p - effective_cost) * q
            row.append(float(prof))
        sensitivity_matrix.append(row)

    regularization_strength = getattr(model, "_regularization_strength", 0.0)

    return ElasticityResult(
        product_code=model.product_code,
        elasticity=model.b,
        optimal_price=optimal_price,
        predicted_units_at_optimal=predicted_units,
        max_profit=max_profit,
        price_grid=[float(p) for p in price_grid],
        profit_grid=[float(v) for v in profits],
        elasticity_ci=elasticity_ci,
        optimal_price_ci=price_ci,
        confidence_level=confidence,
        regularized=bool(regularization_strength),
        regularization_strength=regularization_strength,
        elasticity_bounds=getattr(model, "_elasticity_bounds", None),
        cost_factors=cost_factors,
        sensitivity_matrix=sensitivity_matrix,
        all_negative=all_negative,
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
