import io
import io

from django.test import TestCase

from .bom_loader import BomCsvError, load_bom_from_csv
from .domain_models import (
    BomItem,
    CostBreakdown,
    ElasticityResult,
    FinanceParams,
    InventoryParams,
    LogisticsParams,
    ManufacturingParams,
)
from .pricing_engine import (
    compute_cost_breakdown,
    compute_recommended_price,
    merge_cost_plus_and_ml_price,
    simulate_prices_for_exchange_rates,
)


class BomLoaderTests(TestCase):
    def test_load_bom_from_csv_returns_items(self):
        csv_content = (
            "product_code,part_name,quantity,unit_price_usd\n"
            "P1,Resistor,2,0.1\n"
            "P1,Capacitor,1,0.2\n"
        )
        items = load_bom_from_csv(io.StringIO(csv_content))

        expected = [
            BomItem(product_code="P1", part_name="Resistor", quantity=2, unit_price_usd=0.1),
            BomItem(product_code="P1", part_name="Capacitor", quantity=1, unit_price_usd=0.2),
        ]

        self.assertEqual(items, expected)

    def test_load_bom_from_csv_missing_columns(self):
        csv_content = "product_code,quantity,unit_price_usd\nP1,2,0.1\n"

        with self.assertRaises(BomCsvError):
            load_bom_from_csv(io.StringIO(csv_content))


class PricingEngineTests(TestCase):
    def setUp(self):
        self.bom_items = [
            BomItem(product_code="P1", part_name="Resistor", quantity=2, unit_price_usd=5.0),
            BomItem(product_code="P1", part_name="Capacitor", quantity=1, unit_price_usd=3.0),
        ]
        self.manufacturing = ManufacturingParams(
            smd_cost_per_component=100,
            tht_cost_per_component=50,
            assembly_time_min=30,
            qc_test_time_min=15,
            worker_hour_cost=200,
        )
        self.logistics = LogisticsParams(
            shipping_cost_usd=20,
            custom_clearance_irr=100_000,
            duty_percent=10,
            exchange_rate_buy=50_000,
        )
        self.inventory = InventoryParams(inventory_days=365, capital_cost_rate=10)

    def test_compute_cost_breakdown(self):
        cost_breakdown = compute_cost_breakdown(
            bom_items=self.bom_items,
            manufacturing=self.manufacturing,
            logistics=self.logistics,
            inventory=self.inventory,
        )

        self.assertAlmostEqual(cost_breakdown.bom_cost_irr, 650_000)
        self.assertAlmostEqual(cost_breakdown.assembly_cost_irr, 450)
        self.assertAlmostEqual(cost_breakdown.labor_cost_irr, 150)
        self.assertAlmostEqual(cost_breakdown.logistics_cost_irr, 1_165_000)
        self.assertAlmostEqual(cost_breakdown.inventory_cost_irr, 65_000)

    def test_compute_recommended_price_uses_cost_plus(self):
        cost_breakdown = CostBreakdown(
            bom_cost_irr=650_000,
            assembly_cost_irr=450,
            labor_cost_irr=150,
            logistics_cost_irr=1_165_000,
            inventory_cost_irr=65_000,
        )
        finance = FinanceParams(
            exchange_rate_now=50_000,
            target_margin_percent=20,
            competitor_price_avg=2_000_000,
        )

        price_data = compute_recommended_price(
            cost_breakdown=cost_breakdown, finance=finance
        )

        self.assertAlmostEqual(price_data["final_suggested_price"], 2_256_720)
        self.assertAlmostEqual(price_data["cost_plus_price"], 2_256_720)

    def test_compute_recommended_price_uses_competitor_anchor(self):
        cost_breakdown = CostBreakdown(
            bom_cost_irr=650_000,
            assembly_cost_irr=450,
            labor_cost_irr=150,
            logistics_cost_irr=1_165_000,
            inventory_cost_irr=65_000,
        )
        finance = FinanceParams(
            exchange_rate_now=50_000,
            target_margin_percent=20,
            competitor_price_avg=2_500_000,
        )

        price_data = compute_recommended_price(
            cost_breakdown=cost_breakdown, finance=finance
        )

        self.assertEqual(price_data["final_suggested_price"], 2_500_000)
        self.assertEqual(price_data["cost_plus_price"], 2_500_000)

    def test_compute_recommended_price_adds_elasticity_fields(self):
        cost_breakdown = CostBreakdown(
            bom_cost_irr=500_000,
            assembly_cost_irr=400,
            labor_cost_irr=200,
            logistics_cost_irr=600_000,
            inventory_cost_irr=50_000,
        )
        finance = FinanceParams(
            exchange_rate_now=50_000,
            target_margin_percent=10,
            competitor_price_avg=1_000_000,
        )
        elasticity_result = ElasticityResult(
            elasticity=-1.2, optimal_price=900_000.0, max_profit=400_000.0
        )

        price_data = compute_recommended_price(
            cost_breakdown=cost_breakdown,
            finance=finance,
            elasticity_result=elasticity_result,
        )

        self.assertEqual(price_data["elasticity"], elasticity_result.elasticity)
        self.assertEqual(price_data["optimal_price_ml"], elasticity_result.optimal_price)
        self.assertEqual(price_data["max_profit_ml"], elasticity_result.max_profit)

    def test_merge_cost_plus_and_ml_price_with_elasticity(self):
        cost_plus_price = 2_000_000.0
        elasticity_result = ElasticityResult(
            elasticity=-1.5, optimal_price=1_800_000.0, max_profit=750_000.0
        )

        merged = merge_cost_plus_and_ml_price(cost_plus_price, elasticity_result)

        self.assertIn("optimal_price_ml", merged)
        self.assertAlmostEqual(merged["optimal_price_ml"], elasticity_result.optimal_price)
        self.assertAlmostEqual(
            merged["final_suggested_price"],
            (0.3 * cost_plus_price) + (0.7 * elasticity_result.optimal_price),
        )

    def test_simulate_prices_for_exchange_rates(self):
        rates = [50_000, 60_000, 70_000]
        finance = FinanceParams(exchange_rate_now=50_000, target_margin_percent=10)

        scenarios = simulate_prices_for_exchange_rates(
            bom_items=self.bom_items,
            exchange_rates=rates,
            manufacturing=self.manufacturing,
            logistics=self.logistics,
            inventory=self.inventory,
            finance=finance,
        )

        self.assertEqual(len(scenarios), len(rates))
        costs = [scenario.total_cost_irr for scenario in scenarios]
        self.assertTrue(all(earlier < later for earlier, later in zip(costs, costs[1:])))
