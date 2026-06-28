import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.clients.buff_client import BuffSellOrder, MockBuffClient
from app.clients.discord_client import DiscordWebhookConfig
from app.services.alert_service import AlertServiceConfig
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider
from app.services.pipeline_alert_service import (
    PipelineWithAlertsConfig,
    run_mock_pipeline_with_alerts,
)
from app.services.pipeline_service import EndToEndPipelineConfig
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig

BASE_DIR = Path(__file__).resolve().parents[1]
ORDERS_FIXTURE = BASE_DIR / "tests" / "fixtures" / "pipeline" / "mock_buff_orders.json"
METADATA_FIXTURE = BASE_DIR / "tests" / "fixtures" / "pipeline" / "mock_metadata.json"



def _build_mock_buff_client() -> MockBuffClient:
    payload = json.loads(ORDERS_FIXTURE.read_text(encoding="utf-8"))
    orders = [
        BuffSellOrder(
            listing_id=str(order["listing_id"]),
            goods_id=str(order["goods_id"]),
            market_hash_name=order["market_hash_name"],
            price_cny=Decimal(str(order["price_cny"])),
            float_value=order["float_value"],
            paint_seed=order["paint_seed"],
            inspect_link=order["inspect_link"],
            seller_id=order["seller_id"],
            raw=order["raw"],
        )
        for order in payload
    ]
    return MockBuffClient(sell_orders_by_goods_id={"goods-1": orders})


async def _run() -> None:
    buff_client = _build_mock_buff_client()
    metadata_provider = LocalJsonMetadataProvider(METADATA_FIXTURE)
    pipeline_config = EndToEndPipelineConfig(
        goods_ids=["goods-1"],
        scan_filter_config=ScanFilterConfig(),
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("0.05"),
            min_expected_profit_cny=Decimal("20.00"),
            max_worst_case_loss_pct=Decimal("0.25"),
            min_profit_probability=0.35,
            max_input_total_cost_cny=Decimal("1000.00"),
        ),
    )
    alert_config = PipelineWithAlertsConfig(
        pipeline_config=pipeline_config,
        alert_service_config=AlertServiceConfig(
            alert_only_passed_risk=True,
            enable_dedupe=True,
            urgent_min_roi=None,
            urgent_min_expected_profit_cny=None,
        ),
        discord_config=DiscordWebhookConfig(webhook_url=None, dry_run=True),
    )

    result = await run_mock_pipeline_with_alerts(buff_client, metadata_provider, alert_config)
    pipeline_result = result.pipeline_result

    print(f"scanned candidates count: {len(pipeline_result.scan_result.candidates)}")
    print(f"recipe count: {len(pipeline_result.recipes)}")

    if pipeline_result.recipes:
        recipe = pipeline_result.recipes[0]
        print(f"first recipe hash: {recipe.recipe_hash}")
        print(f"input total cost: {recipe.metrics.input_total_cost_cny}")
        print(f"expected profit: {recipe.metrics.expected_profit_cny}")
        print(f"ROI: {recipe.metrics.roi}")
        print(f"risk passed: {recipe.risk_decision.passed}")
        print(f"risk reason codes: {recipe.risk_decision.reason_codes}")
        if not recipe.risk_decision.passed:
            print("note: risk failed recipes are not alerted by default.")
    else:
        print("first recipe hash: None")
        print("input total cost: None")
        print("expected profit: None")
        print("ROI: None")
        print("risk passed: None")
        print("risk reason codes: []")

    print(f"pipeline errors: {pipeline_result.errors}")
    print(f"recipe alert count: {len(result.recipe_alert_results)}")
    print(f"recipe alert dispatch results: {result.recipe_alert_results}")
    print(f"error alert result: {result.error_alert_result}")



def main() -> None:
    """Run the local mock pipeline with alert dispatch in dry-run mode."""

    asyncio.run(_run())


if __name__ == "__main__":
    main()
