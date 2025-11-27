"""Core pricing calculations."""
from __future__ import annotations

from typing import Iterable

from .domain_models import (
    BomItem,
    CostBreakdown,
    FinanceParams,
    InventoryParams,
    LogisticsParams,
    ManufacturingParams,
    ScenarioResult,
)
from .ml.demand_elasticity import ElasticityResult


def compute_cost_breakdown(
    bom_items: Iterable[BomItem],
    manufacturing: ManufacturingParams,
    logistics: LogisticsParams,
    inventory: InventoryParams,
) -> CostBreakdown:
    """Compute cost components based on inputs."""

    total_components = sum(item.quantity for item in bom_items)
    bom_cost_usd = sum(item.quantity * item.unit_price_usd for item in bom_items)
    bom_cost_irr = bom_cost_usd * logistics.exchange_rate_buy

    assembly_cost_irr = total_components * (
        manufacturing.smd_cost_per_component + manufacturing.tht_cost_per_component
    )

    labor_time_hours = (manufacturing.assembly_time_min + manufacturing.qc_test_time_min) / 60
    labor_cost_irr = labor_time_hours * manufacturing.worker_hour_cost

    logistics_cost_irr = (
        logistics.shipping_cost_usd * logistics.exchange_rate_buy
        + logistics.custom_clearance_irr
        + (logistics.duty_percent / 100) * bom_cost_irr
    )

    inventory_cost_irr = bom_cost_irr * (inventory.inventory_days / 365) * (
        inventory.capital_cost_rate / 100
    )

    return CostBreakdown(
        bom_cost_irr=bom_cost_irr,
        assembly_cost_irr=assembly_cost_irr,
        labor_cost_irr=labor_cost_irr,
        logistics_cost_irr=logistics_cost_irr,
        inventory_cost_irr=inventory_cost_irr,
    )


def compute_recommended_price(
    cost_breakdown: CostBreakdown,
    finance: FinanceParams,
    elasticity_result: ElasticityResult | None = None,
) -> dict[str, float]:
    """Calculate pricing recommendations and related metrics."""

    base_price = cost_breakdown.total_cost_irr * (1 + finance.target_margin_percent / 100)
    competitor_anchor = getattr(finance, "competitor_price_avg", 0) or 0

    cost_plus_price = max(base_price, competitor_anchor)

    result: dict[str, float] = {"cost_plus_price": cost_plus_price}

    merge_result = merge_cost_plus_and_ml_price(cost_plus_price, elasticity_result)
    result.update(merge_result)

    if elasticity_result is not None:
        result.update(
            {
                "elasticity": elasticity_result.elasticity,
                "optimal_price_ml": elasticity_result.optimal_price,
                "max_profit_ml": elasticity_result.max_profit,
            }
        )

    return result


def merge_cost_plus_and_ml_price(
    cost_plus_price: float, elasticity_result: ElasticityResult | None
) -> dict[str, float]:
    """
    Return a dict with:
    - 'cost_plus_price'
    - 'optimal_price_ml' (if elasticity_result is not None)
    - 'final_suggested_price'
      (for now, you can choose average of the two or prefer ML).
    """

    result: dict[str, float] = {"cost_plus_price": cost_plus_price}

    if elasticity_result is not None:
        result["optimal_price_ml"] = elasticity_result.optimal_price

    result["final_suggested_price"] = choose_final_price(cost_plus_price, elasticity_result)

    return result


def choose_final_price(
    cost_plus_price: float,
    elasticity_result: ElasticityResult | None,
) -> float:
    """
    If elasticity_result is None: return cost_plus_price.
    Otherwise, return a compromise between cost-plus and ML optimal price,
    e.g. average of the two or leaning 70% ML / 30% cost-plus.
    """

    if elasticity_result is None:
        return cost_plus_price

    weight_ml = 0.7
    weight_cost_plus = 0.3

    return (weight_ml * elasticity_result.optimal_price) + (
        weight_cost_plus * cost_plus_price
    )


def simulate_prices_for_exchange_rates(
    bom_items: Iterable[BomItem],
    exchange_rates: Iterable[int],
    *,
    manufacturing: ManufacturingParams,
    logistics: LogisticsParams,
    inventory: InventoryParams,
    finance: FinanceParams,
) -> list[ScenarioResult]:
    """Run price simulations for different exchange rates."""

    results: list[ScenarioResult] = []

    for rate in exchange_rates:
        logistics_at_rate = LogisticsParams(
            shipping_cost_usd=logistics.shipping_cost_usd,
            custom_clearance_irr=logistics.custom_clearance_irr,
            duty_percent=logistics.duty_percent,
            exchange_rate_buy=rate,
        )

        finance_at_rate = FinanceParams(
            exchange_rate_now=rate,
            target_margin_percent=finance.target_margin_percent,
            competitor_price_avg=getattr(finance, "competitor_price_avg", 0),
        )

        cost_breakdown = compute_cost_breakdown(
            bom_items=bom_items,
            manufacturing=manufacturing,
            logistics=logistics_at_rate,
            inventory=inventory,
        )

        recommended_price_data = compute_recommended_price(
            cost_breakdown=cost_breakdown,
            finance=finance_at_rate,
        )

        results.append(
                ScenarioResult(
                    exchange_rate=rate,
                    total_cost_irr=cost_breakdown.total_cost_irr,
                    recommended_price_irr=recommended_price_data["final_suggested_price"],
                )
        )

    return results


__all__ = [
    "compute_cost_breakdown",
    "compute_recommended_price",
    "merge_cost_plus_and_ml_price",
    "choose_final_price",
    "simulate_prices_for_exchange_rates",
]
