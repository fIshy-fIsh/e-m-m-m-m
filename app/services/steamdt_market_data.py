from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.clients.steamdt_client import SteamDTPlatformPrice

__all__ = (
    "SteamDTMarketDataClient",
    "SteamDTMarketDataResult",
    "get_steamdt_market_data",
)


class SteamDTMarketDataClient(Protocol):
    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        """Fetch one complete provider-ordered platform collection."""


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTMarketDataResult:
    """Immutable aggregate SteamDT platform data for one requested item."""

    market_hash_name: str
    quotes: tuple[SteamDTPlatformPrice, ...]

    def __post_init__(self) -> None:
        market_hash_name = _canonical_market_hash_name(self.market_hash_name)
        if not isinstance(self.quotes, Sequence) or isinstance(
            self.quotes,
            (str, bytes),
        ):
            raise TypeError("quotes must be a sequence of SteamDTPlatformPrice")
        quotes = tuple(_clone_quote(quote) for quote in self.quotes)
        object.__setattr__(self, "market_hash_name", market_hash_name)
        object.__setattr__(self, "quotes", quotes)


async def get_steamdt_market_data(
    *,
    client: SteamDTMarketDataClient,
    market_hash_name: str,
) -> SteamDTMarketDataResult:
    """Fetch one provider-ordered aggregate platform collection without selection."""

    canonical_name = _canonical_market_hash_name(market_hash_name)
    quotes = await client.get_price_single_candidates(canonical_name)
    if not isinstance(quotes, Sequence) or isinstance(quotes, (str, bytes)):
        raise TypeError("SteamDT market-data client returned an invalid quote sequence")
    return SteamDTMarketDataResult(
        market_hash_name=canonical_name,
        quotes=tuple(quotes),
    )


def _canonical_market_hash_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("market_hash_name must be a string")
    if not value or value != value.strip():
        raise ValueError("market_hash_name must be nonempty without surrounding whitespace")
    return value


def _clone_quote(value: object) -> SteamDTPlatformPrice:
    if type(value) is not SteamDTPlatformPrice:
        raise TypeError("quotes must contain only SteamDTPlatformPrice values")
    return SteamDTPlatformPrice(
        platform=value.platform,
        platform_item_id=value.platform_item_id,
        sell_price_cny=value.sell_price_cny,
        sell_count=value.sell_count,
        bidding_price_cny=value.bidding_price_cny,
        bidding_count=value.bidding_count,
        update_time=value.update_time,
        raw=None,
    )
