import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.clients.buff_client import BuffSellOrder, MockBuffClient
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider
from app.services.pipeline_service import EndToEndPipelineConfig, run_mock_pipeline
from app.services.price_provider import MockPriceProvider, PriceLookupResult, PriceQuote
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig

PIPELINE_METADATA_FIXTURE = Path("tests/fixtures/pipeline/mock_metadata.json")
PIPELINE_ORDERS_FIXTURE = Path("tests/fixtures/pipeline/mock_buff_orders.json")
PIPELINE_STEAMDT_PRICE_FIXTURE = Path("tests/fixtures/pipeline/mock_steamdt_prices.json")



def _make_pipeline_config(
    goods_ids: list[str],
    risk_config: RiskFilterConfig | None = None,
) -> EndToEndPipelineConfig:
    return EndToEndPipelineConfig(
        goods_ids=goods_ids,
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



def _build_mock_price_provider() -> MockPriceProvider:
    payload = json.loads(PIPELINE_STEAMDT_PRICE_FIXTURE.read_text(encoding="utf-8"))
    quotes = {
        item["market_hash_name"]: PriceQuote(
            market_hash_name=item["market_hash_name"],
            price_cny=Decimal(str(item["price_cny"])),
            source=item.get("source", "steamdt-mock"),
            raw=item.get("raw"),
        )
        for item in payload
    }
    return MockPriceProvider(quotes_by_name=quotes)


class MockValuationService:
    async def value_tradeup_results(self, tradeup_results):
        from app.services.valuation_service import ValuationService

        service = ValuationService(_build_mock_price_provider())
        return await service.value_tradeup_results(tradeup_results)


class WarningOnlyValuationService:
    async def value_tradeup_results(self, tradeup_results):
        from app.services.valuation_service import ValuationResult, ValuationWarning

        return ValuationResult(
            tradeup_results=list(tradeup_results),
            missing_market_hash_names=[
                result.output_market_hash_name for result in tradeup_results
            ],
            warnings=[
                ValuationWarning(
                    code="TEST_WARNING",
                    message="valuation mock warning",
                )
            ],
            price_lookup_result=PriceLookupResult(quotes={}, missing=[], errors=[]),
        )


class FailingValuationService:
    async def value_tradeup_results(self, tradeup_results):
        raise RuntimeError("valuation boom")



def test_run_mock_pipeline_without_valuation_service_keeps_original_behavior() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert result.recipes[0].tradeup_results[0].estimated_price_cny == Decimal("0")



def test_run_mock_pipeline_with_valuation_service_updates_output_prices() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=MockValuationService(),
        )
    )

    assert result.recipes[0].tradeup_results[0].estimated_price_cny == Decimal("300.00")
    assert result.recipes[0].tradeup_results[0].expected_value_contribution == Decimal("300.000")



def test_valuation_recomputes_metrics() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=MockValuationService(),
        )
    )

    assert result.recipes[0].metrics.expected_profit_cny == Decimal("147.5000")
    assert result.recipes[0].metrics.roi == Decimal("1.017241379310344827586206897")



def test_valuation_recomputes_risk_decision() -> None:
    permissive_config = _make_pipeline_config(
        ["goods-1"],
        risk_config=RiskFilterConfig(
            min_roi=Decimal("0.01"),
            min_expected_profit_cny=Decimal("20.00"),
            max_worst_case_loss_pct=Decimal("1.00"),
            min_profit_probability=0.10,
            max_input_total_cost_cny=Decimal("1000.00"),
        ),
    )

    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=permissive_config,
            valuation_service=MockValuationService(),
        )
    )

    assert result.recipes[0].risk_decision.passed is True



def test_recipe_hash_remains_unchanged_after_valuation() -> None:
    original = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )
    valued = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=MockValuationService(),
        )
    )

    assert original.recipes[0].recipe_hash == valued.recipes[0].recipe_hash



def test_probability_output_float_and_output_wear_remain_unchanged_after_valuation() -> None:
    original = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )
    valued = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=MockValuationService(),
        )
    )

    assert (
        valued.recipes[0].tradeup_results[0].probability
        == original.recipes[0].tradeup_results[0].probability
    )
    assert (
        valued.recipes[0].tradeup_results[0].output_float
        == original.recipes[0].tradeup_results[0].output_float
    )
    assert (
        valued.recipes[0].tradeup_results[0].output_wear
        == original.recipes[0].tradeup_results[0].output_wear
    )



def test_valuation_warning_is_appended_to_pipeline_errors() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=WarningOnlyValuationService(),
        )
    )

    assert any(error.startswith("valuation warning: TEST_WARNING") for error in result.errors)



def test_valuation_service_error_does_not_crash_pipeline() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
            valuation_service=FailingValuationService(),
        )
    )

    assert result.recipes
    assert any(error.startswith("valuation error:") for error in result.errors)
    assert result.recipes[0].tradeup_results[0].estimated_price_cny == Decimal("0")
