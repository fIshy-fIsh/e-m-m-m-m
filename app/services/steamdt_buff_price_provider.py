from __future__ import annotations

from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.steamdt_buff_price_policy import (
    SteamDTBuffPriceSelectionError,
    select_buff_output_price,
)
from app.services.steamdt_market_data import (
    SteamDTMarketDataClient,
    get_steamdt_market_data,
)

_SOURCE = "steamdt:buff"

__all__ = ("SteamDTBuffPriceProvider",)


class SteamDTBuffPriceProvider:
    """Adapt exact BUFF aggregate sell prices into generic price quotes."""

    def __init__(self, client: SteamDTMarketDataClient) -> None:
        self._client = client

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Compose one aggregate fetch and BUFF selection into a generic quote."""

        market_data = await get_steamdt_market_data(
            client=self._client,
            market_hash_name=market_hash_name,
        )
        selected = select_buff_output_price(market_data=market_data)
        return PriceQuote(
            market_hash_name=selected.market_hash_name,
            price_cny=selected.sell_price_cny,
            source=_SOURCE,
            raw=None,
        )

    async def get_prices(
        self,
        market_hash_names: list[str],
    ) -> PriceLookupResult:
        """Resolve canonical unique names sequentially with per-item isolation."""

        cleaned_names = _clean_market_hash_names(market_hash_names)
        quotes: dict[str, PriceQuote] = {}
        missing: list[str] = []
        errors: list[str] = []
        for index, market_hash_name in enumerate(cleaned_names):
            try:
                quote = await self.get_price(market_hash_name)
            except MemoryError:
                raise
            except SteamDTBuffPriceSelectionError as exc:
                missing.append(market_hash_name)
                errors.append(
                    "STEAMDT_BUFF_PRICE_SELECTION_FAILED: "
                    f"item_index={index}, reason={exc.reason.value}"
                )
            except Exception:
                missing.append(market_hash_name)
                errors.append(
                    f"STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index={index}"
                )
            else:
                if quote.market_hash_name != market_hash_name:
                    missing.append(market_hash_name)
                    errors.append(
                        f"STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index={index}"
                    )
                    continue
                quotes[market_hash_name] = quote
        return PriceLookupResult(quotes=quotes, missing=missing, errors=errors)


def _clean_market_hash_names(market_hash_names: list[str]) -> list[str]:
    if type(market_hash_names) is not list:
        raise TypeError("market_hash_names must be a list of strings")
    cleaned_names: list[str] = []
    seen: set[str] = set()
    for value in market_hash_names:
        if type(value) is not str:
            raise TypeError("market_hash_names must contain only strings")
        canonical_name = value.strip()
        if canonical_name and canonical_name not in seen:
            seen.add(canonical_name)
            cleaned_names.append(canonical_name)
    return cleaned_names
