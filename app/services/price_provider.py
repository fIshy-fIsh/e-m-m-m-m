from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.clients.steamdt_client import (
    SteamDTClient,
    SteamDTPriceQuote,
)


@dataclass(frozen=True)
class PriceQuote:
    """Normalized generic price quote used by valuation components."""

    market_hash_name: str
    price_cny: Decimal
    source: str
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")
        if not self.source.strip():
            raise ValueError("source cannot be empty")


@dataclass(frozen=True)
class PriceLookupResult:
    """Batch lookup result for generic price providers."""

    quotes: dict[str, PriceQuote]
    missing: list[str]
    errors: list[str] = field(default_factory=list)


class PriceProvider(Protocol):
    """Protocol for generic market price providers."""

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Return a single normalized price quote for one market hash name."""

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Return normalized quotes for many market hash names."""


class MockPriceProvider:
    """Deterministic in-memory price provider for unit tests."""

    def __init__(
        self,
        quotes_by_name: dict[str, PriceQuote] | None = None,
        fail_on_single_missing: bool = True,
    ) -> None:
        self.quotes_by_name = quotes_by_name or {}
        self.fail_on_single_missing = fail_on_single_missing

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Return a deterministic single quote or raise if configured to fail."""

        if market_hash_name in self.quotes_by_name:
            return self.quotes_by_name[market_hash_name]
        if self.fail_on_single_missing:
            raise RuntimeError(
                f"missing mock price for market_hash_name: {market_hash_name}"
            )
        raise RuntimeError(
            f"price is missing for market_hash_name: {market_hash_name}"
        )

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Return deterministic batch quotes with missing names preserved."""

        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return PriceLookupResult(quotes=quotes, missing=missing)


class SteamDTPriceProvider:
    """SteamDT-backed adapter from SteamDT client models into generic price quotes."""

    def __init__(self, steamdt_client: SteamDTClient) -> None:
        self.steamdt_client = steamdt_client

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Fetch and convert a single SteamDT price quote into a generic price quote."""

        quote = await self.steamdt_client.get_price_single(market_hash_name)
        return _convert_steamdt_price_quote(quote)

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Fetch and convert multiple SteamDT price quotes into generic price quotes."""

        try:
            batch_result = await self.steamdt_client.get_price_batch(market_hash_names)
        except Exception as exc:
            return PriceLookupResult(
                quotes={},
                missing=list(market_hash_names),
                errors=[str(exc)],
            )

        quotes = {
            name: _convert_steamdt_price_quote(quote)
            for name, quote in batch_result.quotes.items()
        }
        return PriceLookupResult(
            quotes=quotes,
            missing=list(batch_result.missing),
            errors=[],
        )



def _convert_steamdt_price_quote(quote: SteamDTPriceQuote) -> PriceQuote:
    """Convert a SteamDT-specific price quote into the generic price quote model."""

    return PriceQuote(
        market_hash_name=quote.market_hash_name,
        price_cny=quote.price_cny,
        source=quote.source or "steamdt",
        raw=quote.raw,
    )
