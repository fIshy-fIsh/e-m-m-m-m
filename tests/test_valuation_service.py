import asyncio
from decimal import Decimal

from app.services.price_provider import MockPriceProvider, PriceQuote
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import (
    ValuationConfig,
    ValuationMissingPriceStrategy,
    ValuationService,
)


def _make_tradeup_result(
    *,
    name: str = "Output A",
    probability: float = 0.5,
    price: str = "100.00",
    output_float: float = 0.12,
    output_wear: str = "Minimal Wear",
) -> TradeupResult:
    return TradeupResult(
        output_market_hash_name=name,
        probability=probability,
        output_float=output_float,
        output_wear=output_wear,
        estimated_price_cny=Decimal(price),
        expected_value_contribution=Decimal(price) * Decimal(str(probability)),
    )



def _make_price_quote(name: str, price: str) -> PriceQuote:
    return PriceQuote(
        market_hash_name=name,
        price_cny=Decimal(price),
        source="steamdt",
        raw={"source": "test"},
    )



def test_value_tradeup_results_empty_list_returns_empty_and_does_not_call_provider() -> None:
    class NoCallProvider(MockPriceProvider):
        async def get_prices(self, market_hash_names: list[str]):
            raise AssertionError("provider should not be called")

    service = ValuationService(NoCallProvider())

    result = asyncio.run(service.value_tradeup_results([]))

    assert result.tradeup_results == []
    assert result.missing_market_hash_names == []



def test_valuation_updates_estimated_price_when_price_found() -> None:
    provider = MockPriceProvider(
        quotes_by_name={"Output A": _make_price_quote("Output A", "150.00")}
    )
    service = ValuationService(provider)

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result()]))

    assert result.tradeup_results[0].estimated_price_cny == Decimal("150.00")



def test_valuation_recomputes_expected_value_contribution_when_price_found() -> None:
    provider = MockPriceProvider(
        quotes_by_name={"Output A": _make_price_quote("Output A", "150.00")}
    )
    service = ValuationService(provider)

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result(probability=0.25)]))

    assert result.tradeup_results[0].expected_value_contribution == Decimal("37.5000")



def test_probability_output_float_and_output_wear_remain_unchanged() -> None:
    provider = MockPriceProvider(
        quotes_by_name={"Output A": _make_price_quote("Output A", "150.00")}
    )
    original = _make_tradeup_result(probability=0.25, output_float=0.33, output_wear="Field-Tested")
    service = ValuationService(provider)

    result = asyncio.run(service.value_tradeup_results([original]))
    updated = result.tradeup_results[0]

    assert updated.probability == original.probability
    assert updated.output_float == original.output_float
    assert updated.output_wear == original.output_wear



def test_keep_original_strategy_preserves_existing_price_when_missing() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={}),
        ValuationConfig(missing_price_strategy=ValuationMissingPriceStrategy.KEEP_ORIGINAL),
    )

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result(price="111.00")]))

    assert result.tradeup_results[0].estimated_price_cny == Decimal("111.00")



def test_keep_original_strategy_records_warning() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={}),
        ValuationConfig(missing_price_strategy=ValuationMissingPriceStrategy.KEEP_ORIGINAL),
    )

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result()]))

    assert any(warning.code == "MISSING_PRICE_KEEP_ORIGINAL" for warning in result.warnings)



def test_zero_price_strategy_sets_price_to_zero() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={}),
        ValuationConfig(missing_price_strategy=ValuationMissingPriceStrategy.ZERO_PRICE),
    )

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result(price="111.00")]))

    assert result.tradeup_results[0].estimated_price_cny == Decimal("0")
    assert result.tradeup_results[0].expected_value_contribution == Decimal("0.0")



def test_drop_result_strategy_drops_missing_price_result() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={}),
        ValuationConfig(missing_price_strategy=ValuationMissingPriceStrategy.DROP_RESULT),
    )

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result()]))

    assert result.tradeup_results == []
    assert any(warning.code == "MISSING_PRICE_DROPPED" for warning in result.warnings)



def test_require_all_prices_records_warning_when_missing_exists() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={}),
        ValuationConfig(require_all_prices=True),
    )

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result()]))

    assert any(
        warning.code == "REQUIRE_ALL_PRICES_NOT_SATISFIED"
        for warning in result.warnings
    )


class FailingPriceProvider:
    async def get_price(self, market_hash_name: str):
        raise RuntimeError("boom")

    async def get_prices(self, market_hash_names: list[str]):
        raise RuntimeError("boom")



def test_provider_error_does_not_crash_valuation() -> None:
    service = ValuationService(FailingPriceProvider())
    original = _make_tradeup_result()

    result = asyncio.run(service.value_tradeup_results([original]))

    assert result.tradeup_results == [original]
    assert any(warning.code == "PRICE_PROVIDER_ERROR" for warning in result.warnings)



def test_provider_memory_error_propagates_by_identity() -> None:
    failure = MemoryError("memory")

    class MemoryFailingPriceProvider:
        async def get_price(self, market_hash_name: str):
            raise failure

        async def get_prices(self, market_hash_names: list[str]):
            raise failure

    service = ValuationService(MemoryFailingPriceProvider())

    try:
        asyncio.run(service.value_tradeup_results([_make_tradeup_result()]))
    except MemoryError as caught:
        assert caught is failure
    else:
        raise AssertionError("MemoryError should propagate")



def test_missing_market_hash_names_are_recorded_correctly() -> None:
    service = ValuationService(MockPriceProvider(quotes_by_name={}))

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result(name="Output A")]))

    assert result.missing_market_hash_names == ["Output A"]



def test_decimal_precision_is_preserved() -> None:
    provider = MockPriceProvider(
        quotes_by_name={"Output A": _make_price_quote("Output A", "123.4567")}
    )
    service = ValuationService(provider)

    result = asyncio.run(service.value_tradeup_results([_make_tradeup_result(probability=0.25)]))

    assert result.tradeup_results[0].expected_value_contribution == Decimal("30.864175")



def test_price_provider_query_uses_deduplicated_output_names() -> None:
    seen_names: list[list[str]] = []

    class RecordingProvider(MockPriceProvider):
        async def get_prices(self, market_hash_names: list[str]):
            seen_names.append(list(market_hash_names))
            return await super().get_prices(market_hash_names)

    provider = RecordingProvider(
        quotes_by_name={"Output A": _make_price_quote("Output A", "150.00")}
    )
    service = ValuationService(provider)

    asyncio.run(
        service.value_tradeup_results(
            [_make_tradeup_result(name="Output A"), _make_tradeup_result(name="Output A")]
        )
    )

    assert seen_names == [["Output A"]]



def test_output_order_is_preserved_except_for_drop_result() -> None:
    service = ValuationService(
        MockPriceProvider(quotes_by_name={"Output B": _make_price_quote("Output B", "200.00")}),
        ValuationConfig(missing_price_strategy=ValuationMissingPriceStrategy.KEEP_ORIGINAL),
    )

    results = [_make_tradeup_result(name="Output A"), _make_tradeup_result(name="Output B")]
    valued = asyncio.run(service.value_tradeup_results(results))

    assert [result.output_market_hash_name for result in valued.tradeup_results] == [
        "Output A",
        "Output B",
    ]
