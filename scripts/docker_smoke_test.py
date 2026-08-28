import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.clients.buff_client import BuffSellOrder, MockBuffClient
from app.clients.discord_client import DiscordWebhookConfig
from app.jobs.scheduler import (
    cleanup_old_state_job_once,
    heartbeat_job_once,
    run_pipeline_job_once,
)
from app.services.alert_service import AlertServiceConfig
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider
from app.services.pipeline_alert_service import PipelineWithAlertsConfig
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



def _build_pipeline_with_alerts_config() -> PipelineWithAlertsConfig:
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
    return PipelineWithAlertsConfig(
        pipeline_config=pipeline_config,
        alert_service_config=AlertServiceConfig(
            alert_only_passed_risk=True,
            enable_dedupe=True,
        ),
        discord_config=DiscordWebhookConfig(webhook_url=None, dry_run=True),
    )


async def _run() -> None:
    buff_client = _build_mock_buff_client()
    metadata_provider = LocalJsonMetadataProvider(METADATA_FIXTURE)
    pipeline_with_alerts_config = _build_pipeline_with_alerts_config()

    pipeline_result = await run_pipeline_job_once(
        buff_client=buff_client,
        metadata_provider=metadata_provider,
        pipeline_with_alerts_config=pipeline_with_alerts_config,
    )
    heartbeat_result = await heartbeat_job_once(
        discord_config=DiscordWebhookConfig(webhook_url=None, dry_run=True),
        message="docker smoke heartbeat",
    )
    cleanup_result = await cleanup_old_state_job_once()

    print(f"pipeline success: {pipeline_result.success}")
    print(f"heartbeat success: {heartbeat_result.success}")
    print(f"cleanup success: {cleanup_result.success}")



def main() -> None:
    """Run a dry-run-safe scheduler smoke test for Docker validation."""

    asyncio.run(_run())


if __name__ == "__main__":
    main()
