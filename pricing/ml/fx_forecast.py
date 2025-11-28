from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from pricing.services.fx_csv_loader import FxHistoryPoint


@dataclass
class FxForecastResult:
    history_dates: List[dt.date]
    history_rates: List[float]
    forecast_dates: List[dt.date]
    forecast_rates: List[float]
    forecast_low: List[float]
    forecast_high: List[float]
    slope: float
    intercept: float
    r2: float


def fit_linear_trend(points: List[FxHistoryPoint]) -> Tuple[float, float, float]:
    """
    Fit a linear model: rate = intercept + slope * t
    where t is days since the first observation.

    Returns (intercept, slope, r2).
    """
    if len(points) < 5:
        raise ValueError("Need at least 5 FX points to fit a trend.")

    # t = 0,1,2,... based on days since first date
    base_date = points[0].date
    t_vals = np.array([(p.date - base_date).days for p in points], dtype=float)
    y_vals = np.array([p.rate for p in points], dtype=float)

    # Fit: y = a + b t
    X = np.column_stack([np.ones_like(t_vals), t_vals])
    coeff, _, _, _ = np.linalg.lstsq(X, y_vals, rcond=None)
    intercept = float(coeff[0])
    slope = float(coeff[1])

    y_pred = X @ coeff
    y_mean = float(y_vals.mean())
    ss_tot = float(((y_vals - y_mean) ** 2).sum())
    ss_res = float(((y_vals - y_pred) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return intercept, slope, r2


def forecast_fx(
    points: List[FxHistoryPoint],
    horizon_days: int,
    ci_z: float = 1.96,  # ~95% CI
) -> FxForecastResult:
    """
    Forecast FX for the next `horizon_days` days using a linear trend model.

    Returns history + forecast arrays plus simple CI bounds.
    """
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive.")

    intercept, slope, r2 = fit_linear_trend(points)

    base_date = points[0].date
    t_hist = np.array([(p.date - base_date).days for p in points], dtype=float)
    y_hist = np.array([p.rate for p in points], dtype=float)

    # Residual variance for CI
    X_hist = np.column_stack([np.ones_like(t_hist), t_hist])
    y_pred_hist = X_hist @ np.array([intercept, slope])
    ss_res = float(((y_hist - y_pred_hist) ** 2).sum())
    dof = max(len(y_hist) - 2, 1)
    sigma = (ss_res / dof) ** 0.5 if dof > 0 else 0.0

    # History arrays
    history_dates = [p.date for p in points]
    history_rates = [p.rate for p in points]

    # Forecast days: from last date + 1 up to horizon_days
    last_date = points[-1].date
    t_start = (last_date - base_date).days + 1
    t_forecast = np.arange(t_start, t_start + horizon_days, dtype=float)

    forecast_dates: List[dt.date] = [
        last_date + dt.timedelta(days=int(i)) for i in range(1, horizon_days + 1)
    ]
    forecast_rates: List[float] = []
    forecast_low: List[float] = []
    forecast_high: List[float] = []

    for t in t_forecast:
        y_hat = intercept + slope * t
        forecast_rates.append(float(y_hat))
        forecast_low.append(float(y_hat - ci_z * sigma))
        forecast_high.append(float(y_hat + ci_z * sigma))

    return FxForecastResult(
        history_dates=history_dates,
        history_rates=history_rates,
        forecast_dates=forecast_dates,
        forecast_rates=forecast_rates,
        forecast_low=forecast_low,
        forecast_high=forecast_high,
        slope=slope,
        intercept=intercept,
        r2=r2,
    )
