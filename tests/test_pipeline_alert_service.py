import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.clients.buff_client import BuffSellOrder, DryRunBuffClient, MockBuffClient
from app.clients.discord_client import DiscordWebhookConfig
from app.services.alert_service import AlertServiceConfig
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider
from app.services.pipeline_alert_service import (
    PipelineWithAlertsConfig,
    PipelineWithAlertsResult,
    run_mock_pipeline_with_alerts,
)
from app.services.pipeline_service import EndToEndPipelineConfig
from app.services.price_provider import MockPriceProvider, PriceLookupResult, PriceQuote
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.valuation_service import ValuationResult, ValuationService, ValuationWarning

PIPELINE_METADATA_FIXTURE = Path("tests/fixtures/pipeline/mock_metadata.json")
PIPELINE_ORDERS_FIXTURE = Path("tests/fixtures/pipeline/mock_buff_orders.json")



def _make_pipeline_config(
    risk_config: RiskFilterConfig | None = None,
) -> EndToEndPipelineConfig:
    return EndToEndPipelineConfig(
        goods_ids=["goods-1"],
        scan_filter_config=ScanFilterConfig(),
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        risk_config=risk_config
        or RiskFilterConfig(
            min_roi=Decimal("0.05"),
            min_expected_profit_cny=Decimal("20.00"),
            max_worst_case_loss_pct=Decimal("0.25"),
            min_profit_probability=0.35,
            max_input_total_cost_cny=Decimal("1000.00"),
        ),
    )



def _make_alerts_config(
    *,
    alert_only_passed_risk: bool = True,
    risk_config: RiskFilterConfig | None = None,
) -> PipelineWithAlertsConfig:
    return PipelineWithAlertsConfig(
        pipeline_config=_make_pipeline_config(risk_config=risk_config),
        alert_service_config=AlertServiceConfig(
            alert_only_passed_risk=alert_only_passed_risk,
            enable_dedupe=True,
        ),
        discord_config=DiscordWebhookConfig(webhook_url=None, dry_run=True),
    )



def _load_mock_orders() -> list[dict[str, object]]:
    return json.loads(PIPELINE_ORDERS_FIXTURE.read_text(encoding="utf-8"))



def _build_mock_buff_client() -> MockBuffClient:
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
        for order in _load_mock_orders()
    ]
    return MockBuffClient(sell_orders_by_goods_id={"goods-1": orders})



def _build_valuation_service() -> ValuationService:
    price_provider = MockPriceProvider(
        quotes_by_name={
            "Output Skin A": PriceQuote(
                market_hash_name="Output Skin A",
                price_cny=Decimal("300.00"),
                source="steamdt-mock",
                raw={"note": "alert pipeline valuation test"},
            )
        }
    )
    return ValuationService(price_provider)


class FailingMetadataProvider:
    async def fetch_skins(self):
        raise RuntimeError("metadata failure")


class FailingValuationService:
    async def value_tradeup_results(self, tradeup_results):
        raise RuntimeError("valuation boom")


class WarningOnlyValuationService:
    async def value_tradeup_results(self, tradeup_results):
        return ValuationResult(
            tradeup_results=list(tradeup_results),
            missing_market_hash_names=[
                result.output_market_hash_name for result in tradeup_results
            ],
            warnings=[
                ValuationWarning(
                    code="TEST_WARNING",
                    message="valuation warning from alert pipeline",
                )
            ],
            price_lookup_result=PriceLookupResult(quotes={}, missing=[], errors=[]),
        )



def test_run_mock_pipeline_with_alerts_runs_successfully() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(),
        )
    )

    assert isinstance(result, PipelineWithAlertsResult)
    assert result.pipeline_result.recipes
    assert result.started_at.tzinfo is not None
    assert result.finished_at.tzinfo is not None



def test_risk_failed_recipe_is_not_sent_by_default() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=True),
            valuation_service=_build_valuation_service(),
        )
    )

    if not result.pipeline_result.recipes[0].risk_decision.passed:
        assert result.recipe_alert_results == []



def test_risk_failed_recipe_is_sent_when_allowed() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert result.recipe_alert_results
    assert result.recipe_alert_results[0].dry_run is True
    assert result.recipe_alert_results[0].sent is True



def test_risk_passed_recipe_is_sent() -> None:
    permissive_risk = RiskFilterConfig(
        min_roi=Decimal("0.01"),
        min_expected_profit_cny=Decimal("20.00"),
        max_worst_case_loss_pct=Decimal("1.00"),
        min_profit_probability=0.10,
        max_input_total_cost_cny=Decimal("1000.00"),
    )
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(
                alert_only_passed_risk=True,
                risk_config=permissive_risk,
            ),
            valuation_service=_build_valuation_service(),
        )
    )

    assert result.pipeline_result.recipes[0].risk_decision.passed is True
    assert result.recipe_alert_results
    assert result.recipe_alert_results[0].sent is True



def test_pipeline_errors_trigger_error_alert() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=FailingMetadataProvider(),
            config=_make_alerts_config(),
            valuation_service=_build_valuation_service(),
        )
    )

    assert result.pipeline_result.errors
    assert result.error_alert_result is not None
    assert result.error_alert_result.sent is True
    assert result.error_alert_result.dry_run is True



def test_pipeline_without_errors_does_not_send_error_alert() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert result.pipeline_result.errors == []
    assert result.error_alert_result is None



def test_single_recipe_alert_failure_does_not_crash_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import pipeline_alert_service
    from app.services.alert_service import AlertService

    async def failing_send_recipe_alert(self, recipe):
        raise RuntimeError("alert failure")

    monkeypatch.setattr(AlertService, "send_recipe_alert", failing_send_recipe_alert)

    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert isinstance(result, pipeline_alert_service.PipelineWithAlertsResult)
    assert any("Recipe alert failed" in error for error in result.pipeline_result.errors)



def test_dedupe_can_skip_duplicate_recipe_alerts() -> None:
    from app.clients.discord_client import DiscordWebhookClient
    from app.services.alert_service import AlertService, InMemoryAlertDedupeStore

    recipe = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    ).pipeline_result.recipes[0]

    service = AlertService(
        discord_client=DiscordWebhookClient(DiscordWebhookConfig(webhook_url=None, dry_run=True)),
        config=AlertServiceConfig(alert_only_passed_risk=False, enable_dedupe=True),
        dedupe_store=InMemoryAlertDedupeStore(),
    )

    first = asyncio.run(service.send_recipe_alert(recipe))
    second = asyncio.run(service.send_recipe_alert(recipe))

    assert first is not None and first.sent is True
    assert second is not None and second.sent is False
    assert second.message == "Skipped duplicate alert"



def test_pipeline_alert_service_can_use_valuation_service() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert (
        result.pipeline_result.recipes[0].tradeup_results[0].estimated_price_cny
        == Decimal("300.00")
    )
    assert result.pipeline_result.recipes[0].metrics.expected_profit_cny == Decimal("147.5000")



def test_pipeline_alert_service_preserves_recipe_hash_after_valuation() -> None:
    original = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
        )
    )
    valued = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert (
        original.pipeline_result.recipes[0].recipe_hash
        == valued.pipeline_result.recipes[0].recipe_hash
    )



def test_pipeline_alert_service_preserves_probability_float_and_wear_after_valuation() -> None:
    original = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
        )
    )
    valued = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=_build_valuation_service(),
        )
    )

    assert (
        valued.pipeline_result.recipes[0].tradeup_results[0].probability
        == original.pipeline_result.recipes[0].tradeup_results[0].probability
    )
    assert (
        valued.pipeline_result.recipes[0].tradeup_results[0].output_float
        == original.pipeline_result.recipes[0].tradeup_results[0].output_float
    )
    assert (
        valued.pipeline_result.recipes[0].tradeup_results[0].output_wear
        == original.pipeline_result.recipes[0].tradeup_results[0].output_wear
    )



def test_pipeline_alert_service_records_valuation_warning() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=WarningOnlyValuationService(),
        )
    )

    assert any(
        error.startswith("valuation warning: TEST_WARNING")
        for error in result.pipeline_result.errors
    )



def test_pipeline_alert_service_survives_valuation_error() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(alert_only_passed_risk=False),
            valuation_service=FailingValuationService(),
        )
    )

    assert result.pipeline_result.recipes
    assert any(
        error.startswith("valuation error:")
        for error in result.pipeline_result.errors
    )



def test_run_mock_pipeline_script_is_importable() -> None:
    import scripts.run_mock_pipeline as run_mock_pipeline_script

    assert hasattr(run_mock_pipeline_script, "main")



def test_pipeline_alert_service_with_dry_run_client_and_valuation_remains_safe() -> None:
    result = asyncio.run(
        run_mock_pipeline_with_alerts(
            buff_client=DryRunBuffClient(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_alerts_config(),
            valuation_service=_build_valuation_service(),
        )
    )

    assert result.pipeline_result.scan_result.candidates == []
    assert result.recipe_alert_results == []
    assert result.error_alert_result is None
