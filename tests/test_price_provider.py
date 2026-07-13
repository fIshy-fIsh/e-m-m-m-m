import asyncio
from decimal import Decimal

import pytest

from app.clients.steamdt_client import (
    MockSteamDTClient,
    SteamDTAvgPrice,
    SteamDTBatchPriceResult,
    SteamDTPriceQuote,
)
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceQuote,
    SteamDTPriceProvider,
    SteamDTPriceProviderConfig,
)


def _make_price_quote(name: str = "AK-47 | Redline") -> PriceQuote:
    return PriceQuote(
        market_hash_name=name,
        price_cny=Decimal("123.45"),
        source="steamdt",
        raw={"source": "test"},
    )



def _make_steamdt_quote(
    name: str = "AK-47 | Redline",
    price_cny: str = "123.45",
) -> SteamDTPriceQuote:
    return SteamDTPriceQuote(
        market_hash_name=name,
        price_cny=Decimal(price_cny),
        source="steamdt",
        raw={"source": "test"},
    )



class RecordingSteamDTClient:
    def __init__(
        self,
        quotes_by_name: dict[str, SteamDTPriceQuote] | None = None,
        avg_prices_by_name: dict[str, Decimal | None] | None = None,
        fail_avg_for: set[str] | None = None,
        avg_error_message: str = "boom",
        fail_batch: bool = False,
    ) -> None:
        self.quotes_by_name = quotes_by_name or {}
        self.avg_prices_by_name = avg_prices_by_name or {}
        self.fail_avg_for = fail_avg_for or set()
        self.avg_error_message = avg_error_message
        self.fail_batch = fail_batch
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []
        self.avg_calls: list[str] = []
        self.single_selection_calls: list[dict[str, object]] = []
        self.batch_selection_calls: list[dict[str, object]] = []

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        self.single_calls.append(market_hash_name)
        return self.quotes_by_name[market_hash_name]

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        self.batch_calls.append(list(market_hash_names))
        if self.fail_batch:
            raise RuntimeError(self.avg_error_message)
        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing)

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        self.avg_calls.append(market_hash_name)
        if market_hash_name in self.fail_avg_for:
            raise RuntimeError(self.avg_error_message)
        return SteamDTAvgPrice(
            market_hash_name=market_hash_name,
            avg_price_cny=self.avg_prices_by_name.get(market_hash_name),
            platform_avg_prices={},
        )

    async def get_price_single_with_selection(
        self,
        market_hash_name: str,
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
    ) -> SteamDTPriceQuote:
        self.single_selection_calls.append(
            {
                "market_hash_name": market_hash_name,
                "selection_config": selection_config,
                "avg_price_cny": avg_price_cny,
            }
        )
        return self.quotes_by_name[market_hash_name]

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> SteamDTBatchPriceResult:
        self.batch_selection_calls.append(
            {
                "market_hash_names": list(market_hash_names),
                "selection_config": selection_config,
                "avg_prices_by_name": avg_prices_by_name,
            }
        )
        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing)



class BasicSteamDTClient:
    def __init__(
        self,
        quotes_by_name: dict[str, SteamDTPriceQuote],
        avg_prices_by_name: dict[str, Decimal | None] | None = None,
    ) -> None:
        self.quotes_by_name = quotes_by_name
        self.avg_prices_by_name = avg_prices_by_name or {}
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []
        self.avg_calls: list[str] = []

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        self.single_calls.append(market_hash_name)
        return self.quotes_by_name[market_hash_name]

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        self.batch_calls.append(list(market_hash_names))
        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing)

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        self.avg_calls.append(market_hash_name)
        return SteamDTAvgPrice(
            market_hash_name=market_hash_name,
            avg_price_cny=self.avg_prices_by_name.get(market_hash_name),
            platform_avg_prices={},
        )



class NoAvgSteamDTClient:
    def __init__(self, quotes_by_name: dict[str, SteamDTPriceQuote]) -> None:
        self.quotes_by_name = quotes_by_name
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []
        self.single_selection_calls: list[dict[str, object]] = []
        self.batch_selection_calls: list[dict[str, object]] = []

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        self.single_calls.append(market_hash_name)
        return self.quotes_by_name[market_hash_name]

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        self.batch_calls.append(list(market_hash_names))
        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing)

    async def get_price_single_with_selection(
        self,
        market_hash_name: str,
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
    ) -> SteamDTPriceQuote:
        self.single_selection_calls.append(
            {
                "market_hash_name": market_hash_name,
                "selection_config": selection_config,
                "avg_price_cny": avg_price_cny,
            }
        )
        return self.quotes_by_name[market_hash_name]

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> SteamDTBatchPriceResult:
        self.batch_selection_calls.append(
            {
                "market_hash_names": list(market_hash_names),
                "selection_config": selection_config,
                "avg_prices_by_name": avg_prices_by_name,
            }
        )
        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing)



class FailingSteamDTClient:
    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        raise RuntimeError("boom")

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        raise RuntimeError("boom")

    async def get_base_item_info(self, market_hash_name: str) -> object:
        raise RuntimeError("boom")

    async def get_kline(self, market_hash_name: str) -> list[object]:
        raise RuntimeError("boom")

    async def get_wear_info(self, inspect_link: str) -> object:
        raise RuntimeError("boom")



def test_price_quote_creates_successfully() -> None:
    quote = _make_price_quote()

    assert quote.market_hash_name == "AK-47 | Redline"



def test_price_quote_raises_when_market_hash_name_empty() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        PriceQuote(market_hash_name="", price_cny=Decimal("1"), source="steamdt")



def test_price_quote_raises_when_price_negative() -> None:
    with pytest.raises(ValueError, match="price_cny"):
        PriceQuote(
            market_hash_name="AK-47 | Redline",
            price_cny=Decimal("-1"),
            source="steamdt",
        )



def test_price_quote_raises_when_source_empty() -> None:
    with pytest.raises(ValueError, match="source"):
        PriceQuote(
            market_hash_name="AK-47 | Redline",
            price_cny=Decimal("1"),
            source="",
        )



def test_price_lookup_result_creates_successfully() -> None:
    result = PriceLookupResult(quotes={}, missing=[])

    assert result.quotes == {}



def test_steamdt_price_provider_config_defaults() -> None:
    config = SteamDTPriceProviderConfig()

    assert config.selection_config is None
    assert config.enable_avg_sanity_check is False
    assert config.fail_closed_on_avg_error is True
    assert config.max_avg_requests_per_batch == 10



def test_steamdt_price_provider_config_rejects_negative_batch_avg_limit() -> None:
    with pytest.raises(ValueError, match="max_avg_requests_per_batch"):
        SteamDTPriceProviderConfig(max_avg_requests_per_batch=-1)



def test_mock_price_provider_get_price_returns_quote() -> None:
    provider = MockPriceProvider(quotes_by_name={"A": _make_price_quote("A")})

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"



def test_mock_price_provider_get_price_raises_when_missing() -> None:
    provider = MockPriceProvider()

    with pytest.raises(RuntimeError, match="missing mock price"):
        asyncio.run(provider.get_price("A"))



def test_mock_price_provider_get_prices_returns_quotes_and_missing() -> None:
    provider = MockPriceProvider(quotes_by_name={"A": _make_price_quote("A")})

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert "A" in result.quotes
    assert result.missing == ["B"]



def test_steamdt_price_provider_get_price_converts_quote() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_price("A"))

    assert isinstance(result, PriceQuote)
    assert result.market_hash_name == "A"
    assert result.price_cny == Decimal("123.45")



def test_steamdt_price_provider_get_price_rejects_empty_name() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    with pytest.raises(ValueError, match="market_hash_name"):
        asyncio.run(provider.get_price(" "))



def test_steamdt_price_provider_get_prices_converts_batch_result() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert "A" in result.quotes
    assert result.missing == ["B"]



def test_steamdt_price_provider_get_prices_returns_empty_for_empty_names() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices([]))

    assert result == PriceLookupResult(quotes={}, missing=[], errors=[])



def test_steamdt_price_provider_get_prices_strips_empty_names_and_deduplicates() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A"), "B": _make_steamdt_quote("B")}
    )
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices(["A", "", " B ", "A", "  "]))

    assert list(result.quotes.keys()) == ["A", "B"]
    assert client.batch_calls == [["A", "B"]]



def test_steamdt_price_provider_default_does_not_call_avg_price_for_single() -> None:
    client = RecordingSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"
    assert client.avg_calls == []
    assert client.single_calls == ["A"]
    assert client.single_selection_calls == []



def test_steamdt_price_provider_default_does_not_call_avg_price_for_batch() -> None:
    client = RecordingSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices(["A"]))

    assert "A" in result.quotes
    assert client.avg_calls == []
    assert client.batch_calls == [["A"]]
    assert client.batch_selection_calls == []



def test_steamdt_price_provider_get_price_calls_avg_and_selection_when_enabled() -> None:
    selection_config = SteamDTPriceSelectionConfig(fallback_to_lowest_positive=False)
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        avg_prices_by_name={"A": Decimal("100.00")},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            selection_config=selection_config,
            enable_avg_sanity_check=True,
        ),
    )

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"
    assert client.avg_calls == ["A"]
    assert client.single_calls == []
    assert len(client.single_selection_calls) == 1
    assert client.single_selection_calls[0]["selection_config"] is selection_config
    assert client.single_selection_calls[0]["avg_price_cny"] == Decimal("100.00")



def test_steamdt_price_provider_get_prices_calls_avg_and_batch_selection_when_enabled() -> None:
    selection_config = SteamDTPriceSelectionConfig(fallback_to_lowest_positive=False)
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A"), "B": _make_steamdt_quote("B")},
        avg_prices_by_name={"A": Decimal("100.00"), "B": Decimal("200.00")},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            selection_config=selection_config,
            enable_avg_sanity_check=True,
        ),
    )

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert list(result.quotes.keys()) == ["A", "B"]
    assert client.avg_calls == ["A", "B"]
    assert client.batch_calls == []
    assert len(client.batch_selection_calls) == 1
    assert client.batch_selection_calls[0]["selection_config"] is selection_config
    assert client.batch_selection_calls[0]["avg_prices_by_name"] == {
        "A": Decimal("100.00"),
        "B": Decimal("200.00"),
    }



def test_steamdt_price_provider_get_price_avg_failure_fail_closed_raises() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        fail_avg_for={"A"},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    with pytest.raises(RuntimeError, match="AVG_SANITY_AVG_REQUEST_FAILED"):
        asyncio.run(provider.get_price("A"))

    assert client.single_selection_calls == []
    assert client.single_calls == []



def test_steamdt_price_provider_get_price_avg_failure_open_continues_without_avg() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        fail_avg_for={"A"},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            enable_avg_sanity_check=True,
            fail_closed_on_avg_error=False,
        ),
    )

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"
    assert client.single_selection_calls[0]["avg_price_cny"] is None



def test_steamdt_price_provider_get_prices_avg_failure_fail_closed_returns_errors() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A"), "B": _make_steamdt_quote("B")},
        fail_avg_for={"B"},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert result.quotes == {}
    assert result.missing == ["A", "B"]
    assert any("AVG_SANITY_AVG_REQUEST_FAILED" in error for error in result.errors)
    assert client.batch_selection_calls == []
    assert client.batch_calls == []



def test_steamdt_price_provider_get_prices_avg_failure_open_continues_selection() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A"), "B": _make_steamdt_quote("B")},
        avg_prices_by_name={"A": Decimal("100.00")},
        fail_avg_for={"B"},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            enable_avg_sanity_check=True,
            fail_closed_on_avg_error=False,
        ),
    )

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert list(result.quotes.keys()) == ["A", "B"]
    assert result.errors
    assert client.batch_selection_calls[0]["avg_prices_by_name"] == {
        "A": Decimal("100.00")
    }



def test_steamdt_price_provider_get_prices_avg_limit_returns_error_without_requests() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A"), "B": _make_steamdt_quote("B")}
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            enable_avg_sanity_check=True,
            max_avg_requests_per_batch=1,
        ),
    )

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert result.quotes == {}
    assert result.missing == ["A", "B"]
    assert result.errors == ["AVG_SANITY_BATCH_LIMIT_EXCEEDED: requested=2, limit=1"]
    assert client.avg_calls == []
    assert client.batch_calls == []
    assert client.batch_selection_calls == []



def test_steamdt_price_provider_falls_back_to_get_price_single_without_selection_method() -> None:
    client = BasicSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        avg_prices_by_name={"A": Decimal("100.00")},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"
    assert client.avg_calls == ["A"]
    assert client.single_calls == ["A"]



def test_steamdt_price_provider_falls_back_to_get_price_batch_without_selection_method() -> None:
    client = BasicSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        avg_prices_by_name={"A": Decimal("100.00")},
    )
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    result = asyncio.run(provider.get_prices(["A"]))

    assert "A" in result.quotes
    assert client.avg_calls == ["A"]
    assert client.batch_calls == [["A"]]



def test_steamdt_price_provider_no_avg_support_fail_closed_for_single_raises() -> None:
    client = NoAvgSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    with pytest.raises(RuntimeError, match="AVG_SANITY_UNSUPPORTED"):
        asyncio.run(provider.get_price("A"))

    assert client.single_selection_calls == []



def test_steamdt_price_provider_no_avg_support_open_continues_single_selection() -> None:
    client = NoAvgSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            enable_avg_sanity_check=True,
            fail_closed_on_avg_error=False,
        ),
    )

    result = asyncio.run(provider.get_price("A"))

    assert result.market_hash_name == "A"
    assert client.single_selection_calls[0]["avg_price_cny"] is None



def test_steamdt_price_provider_no_avg_support_fail_closed_for_batch_returns_errors() -> None:
    client = NoAvgSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(enable_avg_sanity_check=True),
    )

    result = asyncio.run(provider.get_prices(["A"]))

    assert result.quotes == {}
    assert result.missing == ["A"]
    assert result.errors == [
        "AVG_SANITY_UNSUPPORTED: SteamDT client does not support get_avg_price"
    ]
    assert client.batch_selection_calls == []



def test_steamdt_price_provider_no_avg_support_open_continues_batch_selection() -> None:
    client = NoAvgSteamDTClient(quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(
        client,
        SteamDTPriceProviderConfig(
            enable_avg_sanity_check=True,
            fail_closed_on_avg_error=False,
        ),
    )

    result = asyncio.run(provider.get_prices(["A"]))

    assert "A" in result.quotes
    assert result.errors == [
        "AVG_SANITY_UNSUPPORTED: SteamDT client does not support get_avg_price"
    ]
    assert client.batch_selection_calls[0]["avg_prices_by_name"] == {}



def test_steamdt_price_provider_get_prices_returns_errors_when_client_fails() -> None:
    provider = SteamDTPriceProvider(FailingSteamDTClient())

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert result.quotes == {}
    assert result.missing == ["A", "B"]
    assert result.errors



def test_steamdt_price_provider_get_prices_error_redacts_authorization_bearer() -> None:
    client = RecordingSteamDTClient(
        quotes_by_name={"A": _make_steamdt_quote("A")},
        avg_error_message="Authorization: Bearer super-secret-steamdt-key",
        fail_batch=True,
    )
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices(["A"]))

    assert result.errors
    assert "super-secret-steamdt-key" not in result.errors[0]
    assert "Authorization: Bearer [REDACTED]" in result.errors[0]
