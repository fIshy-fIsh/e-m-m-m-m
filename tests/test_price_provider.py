import asyncio
from decimal import Decimal

import pytest

from app.clients.steamdt_client import (
    MockSteamDTClient,
    SteamDTPriceQuote,
)
from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceQuote,
    SteamDTPriceProvider,
)


def _make_price_quote(name: str = "AK-47 | Redline") -> PriceQuote:
    return PriceQuote(
        market_hash_name=name,
        price_cny=Decimal("123.45"),
        source="steamdt",
        raw={"source": "test"},
    )



def _make_steamdt_quote(name: str = "AK-47 | Redline") -> SteamDTPriceQuote:
    return SteamDTPriceQuote(
        market_hash_name=name,
        price_cny=Decimal("123.45"),
        source="steamdt",
        raw={"source": "test"},
    )



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



def test_steamdt_price_provider_get_prices_converts_batch_result() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_steamdt_quote("A")})
    provider = SteamDTPriceProvider(client)

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert "A" in result.quotes
    assert result.missing == ["B"]


class FailingSteamDTClient:
    async def get_price_single(self, market_hash_name: str):
        raise RuntimeError("boom")

    async def get_price_batch(self, market_hash_names: list[str]):
        raise RuntimeError("boom")

    async def get_base_item_info(self, market_hash_name: str):
        raise RuntimeError("boom")

    async def get_kline(self, market_hash_name: str):
        raise RuntimeError("boom")

    async def get_wear_info(self, inspect_link: str):
        raise RuntimeError("boom")



def test_steamdt_price_provider_get_prices_returns_errors_when_client_fails() -> None:
    provider = SteamDTPriceProvider(FailingSteamDTClient())

    result = asyncio.run(provider.get_prices(["A", "B"]))

    assert result.quotes == {}
    assert result.missing == ["A", "B"]
    assert result.errors
