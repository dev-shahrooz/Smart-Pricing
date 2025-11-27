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


__all__ = ["compute_cost_breakdown", "compute_recommended_price"]
