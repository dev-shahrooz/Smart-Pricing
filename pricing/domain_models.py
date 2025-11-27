"""Domain models for pricing inputs."""
from dataclasses import dataclass

from .ml.demand_elasticity import ElasticityResult


@dataclass
class ProductInfo:
    product_name: str
    product_code: str
    category: str | None = None


@dataclass
class ManufacturingParams:
    smd_cost_per_component: int  # IRR
    tht_cost_per_component: int  # IRR
    assembly_time_min: float
    qc_test_time_min: float
    worker_hour_cost: int  # IRR


@dataclass
class LogisticsParams:
    shipping_cost_usd: float
    custom_clearance_irr: int
    duty_percent: float
    exchange_rate_buy: int


@dataclass
class InventoryParams:
    inventory_days: int
    capital_cost_rate: float


@dataclass
class MarketParams:
    competitor_price_avg: int
    elasticity: float | None = None


@dataclass
class FinanceParams:
    exchange_rate_now: int
    target_margin_percent: float
    competitor_price_avg: float = 0


@dataclass
class BomItem:
    product_code: str
    part_name: str
    quantity: int
    unit_price_usd: float


@dataclass
class CostBreakdown:
    bom_cost_irr: float
    assembly_cost_irr: float
    labor_cost_irr: float
    logistics_cost_irr: float
    inventory_cost_irr: float

    @property
    def total_cost_irr(self) -> float:
        return (
            self.bom_cost_irr
            + self.assembly_cost_irr
            + self.labor_cost_irr
            + self.logistics_cost_irr
            + self.inventory_cost_irr
        )


@dataclass
class ScenarioResult:
    exchange_rate: int
    total_cost_irr: float
    recommended_price_irr: float
