from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.clients.buff_client import BuffClient
from app.clients.discord_client import (
    AlertDispatchResult,
    DiscordWebhookClient,
    DiscordWebhookConfig,
)
from app.services.alert_service import AlertService, AlertServiceConfig
from app.services.metadata_provider import MetadataProvider
from app.services.pipeline_service import (
    EndToEndPipelineConfig,
    EndToEndPipelineResult,
    run_mock_pipeline,
)
from app.services.valuation_service import ValuationService


@dataclass(frozen=True)
class PipelineWithAlertsConfig:
    """Configuration for running the mock pipeline and dispatching alerts."""

    pipeline_config: EndToEndPipelineConfig
    alert_service_config: AlertServiceConfig
    discord_config: DiscordWebhookConfig

    def __post_init__(self) -> None:
        if self.pipeline_config is None:
            raise ValueError("pipeline_config must be provided")
        if self.alert_service_config is None:
            raise ValueError("alert_service_config must be provided")
        if self.discord_config is None:
            raise ValueError("discord_config must be provided")


@dataclass(frozen=True)
class PipelineWithAlertsResult:
    """Result of a mock pipeline run plus attempted alert dispatches."""

    pipeline_result: EndToEndPipelineResult
    recipe_alert_results: list[AlertDispatchResult]
    error_alert_result: AlertDispatchResult | None
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")


async def run_mock_pipeline_with_alerts(
    buff_client: BuffClient,
    metadata_provider: MetadataProvider,
    config: PipelineWithAlertsConfig,
    *,
    valuation_service: ValuationService | None = None,
) -> PipelineWithAlertsResult:
    """Run the mock pipeline and dispatch recipe/error alerts via Discord webhook client."""

    started_at = datetime.now(UTC)
    pipeline_result = await run_mock_pipeline(
        buff_client=buff_client,
        metadata_provider=metadata_provider,
        config=config.pipeline_config,
        valuation_service=valuation_service,
    )

    discord_client = DiscordWebhookClient(config.discord_config)
    alert_service = AlertService(
        discord_client=discord_client,
        config=config.alert_service_config,
    )

    aggregated_errors = list(pipeline_result.errors)
    recipe_alert_results: list[AlertDispatchResult] = []

    for recipe in pipeline_result.recipes:
        try:
            dispatch_result = await alert_service.send_recipe_alert(recipe)
        except Exception as exc:
            aggregated_errors.append(
                f"Recipe alert failed for recipe_hash={recipe.recipe_hash}: {exc}"
            )
            continue

        if dispatch_result is not None:
            recipe_alert_results.append(dispatch_result)

    error_alert_result: AlertDispatchResult | None = None
    if aggregated_errors:
        try:
            error_alert_result = await alert_service.send_pipeline_error_alert(aggregated_errors)
        except Exception as exc:
            aggregated_errors.append(f"Pipeline error alert failed: {exc}")
            error_alert_result = None

    if aggregated_errors != pipeline_result.errors:
        pipeline_result = replace(pipeline_result, errors=aggregated_errors)

    finished_at = datetime.now(UTC)
    return PipelineWithAlertsResult(
        pipeline_result=pipeline_result,
        recipe_alert_results=recipe_alert_results,
        error_alert_result=error_alert_result,
        started_at=started_at,
        finished_at=finished_at,
    )
