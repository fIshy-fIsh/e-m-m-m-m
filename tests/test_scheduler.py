import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.clients.buff_client import BuffSellOrder, MockBuffClient
from app.clients.discord_client import DiscordWebhookConfig
from app.jobs.scheduler import (
    SchedulerConfig,
    cleanup_old_state_job_once,
    create_scheduler,
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

PIPELINE_METADATA_FIXTURE = Path("tests/fixtures/pipeline/mock_metadata.json")
PIPELINE_ORDERS_FIXTURE = Path("tests/fixtures/pipeline/mock_buff_orders.json")


def _build_mock_buff_client() -> MockBuffClient:
    payload = json.loads(PIPELINE_ORDERS_FIXTURE.read_text(encoding="utf-8"))
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


def test_scheduler_config_creates_successfully() -> None:
    config = SchedulerConfig()

    assert config.scan_interval_seconds == 300



def test_scheduler_config_rejects_non_positive_scan_interval() -> None:
    with pytest.raises(ValueError, match="scan_interval_seconds"):
        SchedulerConfig(scan_interval_seconds=0)



def test_scheduler_config_rejects_non_positive_heartbeat_interval() -> None:
    with pytest.raises(ValueError, match="heartbeat_interval_seconds"):
        SchedulerConfig(heartbeat_interval_seconds=0)



def test_scheduler_config_rejects_non_positive_cleanup_interval() -> None:
    with pytest.raises(ValueError, match="cleanup_interval_seconds"):
        SchedulerConfig(cleanup_interval_seconds=0)



def test_scheduler_config_rejects_max_instances_below_one() -> None:
    with pytest.raises(ValueError, match="max_instances"):
        SchedulerConfig(max_instances=0)



def test_run_pipeline_job_once_succeeds() -> None:
    result = asyncio.run(
        run_pipeline_job_once(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            pipeline_with_alerts_config=_build_pipeline_with_alerts_config(),
        )
    )

    assert result.success is True
    assert "recipes=" in result.message
    assert "alerts=" in result.message
    assert "errors=" in result.message



def test_run_pipeline_job_once_handles_pipeline_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs import scheduler as scheduler_module

    async def failing_pipeline(*args, **kwargs):
        raise RuntimeError("pipeline boom")

    monkeypatch.setattr(scheduler_module, "run_mock_pipeline_with_alerts", failing_pipeline)

    result = asyncio.run(
        run_pipeline_job_once(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            pipeline_with_alerts_config=_build_pipeline_with_alerts_config(),
        )
    )

    assert result.success is False
    assert result.errors



def test_heartbeat_job_once_succeeds_in_dry_run() -> None:
    result = asyncio.run(
        heartbeat_job_once(
            discord_config=DiscordWebhookConfig(webhook_url=None, dry_run=True),
            message="heartbeat",
        )
    )

    assert result.success is True



def test_cleanup_old_state_job_once_is_noop_success() -> None:
    result = asyncio.run(cleanup_old_state_job_once())

    assert result.success is True
    assert result.message == "Cleanup job is a no-op in V1."



def test_create_scheduler_registers_expected_jobs_without_starting() -> None:
    config = SchedulerConfig(
        scan_interval_seconds=10,
        heartbeat_interval_seconds=20,
        cleanup_interval_seconds=30,
    )

    async def pipeline_factory():
        return await cleanup_old_state_job_once()

    async def heartbeat_factory():
        return await cleanup_old_state_job_once()

    async def cleanup_factory():
        return await cleanup_old_state_job_once()

    scheduler = create_scheduler(
        config,
        pipeline_job_factory=pipeline_factory,
        heartbeat_job_factory=heartbeat_factory,
        cleanup_job_factory=cleanup_factory,
    )

    assert isinstance(scheduler, AsyncIOScheduler)
    assert scheduler.running is False
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"pipeline-job", "heartbeat-job", "cleanup-job"}



def test_run_scheduler_once_script_is_importable() -> None:
    import scripts.run_scheduler_once as run_scheduler_once_script

    assert hasattr(run_scheduler_once_script, "main")
