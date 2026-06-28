import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from app.clients.buff_client import BuffClient, BuffSellOrder, MockBuffClient
from app.clients.discord_client import DiscordWebhookClient, DiscordWebhookConfig
from app.config import get_settings
from app.logging_config import configure_logging
from app.services.alert_service import (
    AlertField,
    AlertMessage,
    AlertService,
    AlertServiceConfig,
    AlertSeverity,
)
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider, MetadataProvider
from app.services.pipeline_alert_service import (
    PipelineWithAlertsConfig,
    run_mock_pipeline_with_alerts,
)
from app.services.pipeline_service import EndToEndPipelineConfig
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig


@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration for the V1 mock/dry-run scheduler."""

    scan_interval_seconds: int = 300
    heartbeat_interval_seconds: int = 86400
    cleanup_interval_seconds: int = 86400
    dry_run: bool = True
    run_on_startup: bool = False
    max_instances: int = 1

    def __post_init__(self) -> None:
        if self.scan_interval_seconds <= 0:
            raise ValueError("scan_interval_seconds must be greater than 0")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be greater than 0")
        if self.cleanup_interval_seconds <= 0:
            raise ValueError("cleanup_interval_seconds must be greater than 0")
        if self.max_instances < 1:
            raise ValueError("max_instances must be greater than or equal to 1")


@dataclass(frozen=True)
class SchedulerJobResult:
    """Result payload for a single scheduler job invocation."""

    job_name: str
    success: bool
    message: str
    started_at: datetime
    finished_at: datetime
    errors: list[str]

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")


async def run_pipeline_job_once(
    buff_client: BuffClient,
    metadata_provider: MetadataProvider,
    pipeline_with_alerts_config: PipelineWithAlertsConfig,
) -> SchedulerJobResult:
    """Run the mock pipeline-with-alerts once and summarize the outcome."""

    started_at = datetime.now(UTC)
    try:
        result = await run_mock_pipeline_with_alerts(
            buff_client=buff_client,
            metadata_provider=metadata_provider,
            config=pipeline_with_alerts_config,
        )
        finished_at = datetime.now(UTC)
        message = (
            f"recipes={len(result.pipeline_result.recipes)}, "
            f"alerts={len(result.recipe_alert_results)}, "
            f"errors={len(result.pipeline_result.errors)}"
        )
        return SchedulerJobResult(
            job_name="pipeline",
            success=True,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            errors=result.pipeline_result.errors,
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        return SchedulerJobResult(
            job_name="pipeline",
            success=False,
            message="Pipeline job failed",
            started_at=started_at,
            finished_at=finished_at,
            errors=[str(exc)],
        )


async def heartbeat_job_once(
    discord_config: DiscordWebhookConfig,
    message: str | None = None,
) -> SchedulerJobResult:
    """Send a dry-run-safe heartbeat alert once."""

    started_at = datetime.now(UTC)
    try:
        discord_client = DiscordWebhookClient(discord_config)
        alert_service = AlertService(
            discord_client=discord_client,
            config=AlertServiceConfig(alert_only_passed_risk=False, enable_dedupe=False),
        )
        alert_message = AlertMessage(
            title="CS2 Trade-up Scheduler Heartbeat",
            severity=AlertSeverity.DAILY_SUMMARY,
            content=(
                "service=cs2-buff-tradeup-scanner | "
                f"dry_run={discord_config.dry_run}"
            ),
            fields=[
                AlertField("Service", "cs2-buff-tradeup-scanner"),
                AlertField("Current UTC Time", datetime.now(UTC).isoformat()),
                AlertField("Dry Run", str(discord_config.dry_run)),
                AlertField("Message", message or "Heartbeat"),
            ],
            created_at=datetime.now(UTC),
        )
        dispatch_result = await alert_service.send_alert(alert_message)
        finished_at = datetime.now(UTC)
        return SchedulerJobResult(
            job_name="heartbeat",
            success=True,
            message=f"Heartbeat sent (dry_run={dispatch_result.dry_run})",
            started_at=started_at,
            finished_at=finished_at,
            errors=[],
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        return SchedulerJobResult(
            job_name="heartbeat",
            success=False,
            message="Heartbeat job failed",
            started_at=started_at,
            finished_at=finished_at,
            errors=[str(exc)],
        )


async def cleanup_old_state_job_once() -> SchedulerJobResult:
    """Run the V1 cleanup placeholder job."""

    started_at = datetime.now(UTC)
    finished_at = datetime.now(UTC)
    return SchedulerJobResult(
        job_name="cleanup",
        success=True,
        message="Cleanup job is a no-op in V1.",
        started_at=started_at,
        finished_at=finished_at,
        errors=[],
    )



def create_scheduler(
    config: SchedulerConfig,
    pipeline_job_factory: Callable[[], Awaitable[SchedulerJobResult]] | None = None,
    heartbeat_job_factory: Callable[[], Awaitable[SchedulerJobResult]] | None = None,
    cleanup_job_factory: Callable[[], Awaitable[SchedulerJobResult]] | None = None,
) -> AsyncIOScheduler:
    """Create and register the V1 scheduler jobs without starting the scheduler."""

    scheduler = AsyncIOScheduler(timezone="UTC")

    if pipeline_job_factory is not None:
        scheduler.add_job(
            pipeline_job_factory,
            trigger="interval",
            seconds=config.scan_interval_seconds,
            id="pipeline-job",
            max_instances=config.max_instances,
            coalesce=True,
            misfire_grace_time=60,
        )

    if heartbeat_job_factory is not None:
        scheduler.add_job(
            heartbeat_job_factory,
            trigger="interval",
            seconds=config.heartbeat_interval_seconds,
            id="heartbeat-job",
            max_instances=config.max_instances,
            coalesce=True,
            misfire_grace_time=60,
        )

    if cleanup_job_factory is not None:
        scheduler.add_job(
            cleanup_job_factory,
            trigger="interval",
            seconds=config.cleanup_interval_seconds,
            id="cleanup-job",
            max_instances=config.max_instances,
            coalesce=True,
            misfire_grace_time=60,
        )

    return scheduler



def _build_mock_buff_client_from_fixture(orders_fixture: Path) -> MockBuffClient:
    """Create a MockBuffClient from the pipeline orders fixture."""

    payload = json.loads(orders_fixture.read_text(encoding="utf-8"))
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
    """Build the default mock/dry-run pipeline-with-alerts configuration."""

    settings = get_settings()
    pipeline_config = EndToEndPipelineConfig(
        goods_ids=["goods-1"],
        scan_filter_config=ScanFilterConfig(),
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal(str(settings.trading.sell_fee_rate)),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal(str(settings.trading.min_roi)),
            min_expected_profit_cny=Decimal(str(settings.trading.min_expected_profit_cny)),
            max_worst_case_loss_pct=Decimal(str(settings.trading.max_worst_case_loss_pct)),
            min_profit_probability=settings.trading.min_profit_probability,
            max_input_total_cost_cny=Decimal(str(settings.trading.max_input_total_cost_cny)),
        ),
    )
    return PipelineWithAlertsConfig(
        pipeline_config=pipeline_config,
        alert_service_config=AlertServiceConfig(
            alert_only_passed_risk=True,
            enable_dedupe=True,
        ),
        discord_config=DiscordWebhookConfig(
            webhook_url=settings.discord_webhook_url or None,
            dry_run=settings.dry_run,
            mention_user_id=settings.discord_mention_user_id or None,
            mention_role_id=settings.discord_mention_role_id or None,
        ),
    )


async def main() -> None:
    """Run the mock/dry-run scheduler entrypoint with graceful shutdown support."""

    configure_logging(get_settings().log_level)
    settings = get_settings()
    base_dir = Path(__file__).resolve().parents[2]
    orders_fixture = base_dir / "tests" / "fixtures" / "pipeline" / "mock_buff_orders.json"
    metadata_fixture = base_dir / "tests" / "fixtures" / "pipeline" / "mock_metadata.json"

    buff_client = _build_mock_buff_client_from_fixture(orders_fixture)
    metadata_provider = LocalJsonMetadataProvider(metadata_fixture)
    pipeline_with_alerts_config = _build_pipeline_with_alerts_config()

    scheduler_config = SchedulerConfig(
        scan_interval_seconds=settings.scan_normal_interval_seconds,
        heartbeat_interval_seconds=settings.scheduler.heartbeat_interval_seconds,
        cleanup_interval_seconds=settings.scheduler.cleanup_interval_seconds,
        dry_run=settings.dry_run,
        run_on_startup=settings.scheduler.run_on_startup,
        max_instances=settings.scheduler.max_instances,
    )

    async def pipeline_job_factory() -> SchedulerJobResult:
        return await run_pipeline_job_once(
            buff_client=buff_client,
            metadata_provider=metadata_provider,
            pipeline_with_alerts_config=pipeline_with_alerts_config,
        )

    async def heartbeat_job_factory() -> SchedulerJobResult:
        return await heartbeat_job_once(
            pipeline_with_alerts_config.discord_config,
            message="Scheduler heartbeat",
        )

    async def cleanup_job_factory() -> SchedulerJobResult:
        return await cleanup_old_state_job_once()

    scheduler = create_scheduler(
        scheduler_config,
        pipeline_job_factory=pipeline_job_factory,
        heartbeat_job_factory=heartbeat_job_factory,
        cleanup_job_factory=cleanup_job_factory,
    )

    if scheduler_config.run_on_startup:
        await pipeline_job_factory()

    scheduler.start()
    print(
        "scheduler started "
        f"(scan={scheduler_config.scan_interval_seconds}s, dry_run={scheduler_config.dry_run})"
    )

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scheduler.shutdown(wait=False)
        print("scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
