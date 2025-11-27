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
    MarketParams,
    ScenarioResult,
)


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
    market: MarketParams,
) -> float:
    """Calculate a recommended sales price in IRR."""

    base_price = cost_breakdown.total_cost_irr * (1 + finance.target_margin_percent / 100)
    competitor_anchor = market.competitor_price_avg if market.competitor_price_avg else 0

    return max(base_price, competitor_anchor)


def simulate_prices_for_exchange_rates(
    bom_items: Iterable[BomItem],
    exchange_rates: Iterable[int],
    *,
    manufacturing: ManufacturingParams,
    logistics: LogisticsParams,
    inventory: InventoryParams,
    market: MarketParams,
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
        )

        cost_breakdown = compute_cost_breakdown(
            bom_items=bom_items,
            manufacturing=manufacturing,
            logistics=logistics_at_rate,
            inventory=inventory,
        )

        recommended_price = compute_recommended_price(
            cost_breakdown=cost_breakdown,
            finance=finance_at_rate,
            market=market,
        )

        results.append(
            ScenarioResult(
                exchange_rate=rate,
                total_cost_irr=cost_breakdown.total_cost_irr,
                recommended_price_irr=recommended_price,
            )
        )

    return results


__all__ = [
    "compute_cost_breakdown",
    "compute_recommended_price",
    "simulate_prices_for_exchange_rates",
]
