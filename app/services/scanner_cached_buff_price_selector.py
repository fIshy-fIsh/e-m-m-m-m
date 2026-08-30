"""Strict BUFF cached-price selector for scanner valuation reads.

This adapter matches the selector surface consumed by
``SteamDTCachedPriceResolver`` while delegating all BUFF platform and sell-price
policy decisions to ``select_buff_output_price``. Generic SteamDT selection
configuration and average-price inputs never influence scanner valuation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.clients.steamdt_client import SteamDTPlatformPrice, SteamDTPriceQuote
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    SteamDTPriceSelectionResult,
)
from app.services.steamdt_buff_price_policy import (
    SteamDTBuffPriceSelectionError,
    select_buff_output_price,
)
from app.services.steamdt_market_data import SteamDTMarketDataResult

SCANNER_STRICT_BUFF_SELECTION_STRATEGY = "strict_buff_sell_price"
SCANNER_STRICT_BUFF_SOURCE = "steamdt:buff"

__all__ = (
    "SCANNER_STRICT_BUFF_SELECTION_STRATEGY",
    "SCANNER_STRICT_BUFF_SOURCE",
    "select_scanner_cached_buff_price",
)


def select_scanner_cached_buff_price(
    market_hash_name: str,
    platform_prices: list[SteamDTPlatformPrice],
    *,
    config: SteamDTPriceSelectionConfig | None = None,
    avg_price_cny: Decimal | None = None,
    original_payload: dict[str, Any] | None = None,
) -> SteamDTPriceSelectionResult:
    """Select one exact BUFF sell quote without generic fallback semantics."""

    # These arguments exist only because SteamDTCachedPriceResolver has one
    # generic selector protocol. Scanner valuation policy is intentionally
    # independent of every generic cross-platform selection control.
    del config, avg_price_cny, original_payload

    market_data = SteamDTMarketDataResult(
        market_hash_name=market_hash_name,
        quotes=tuple(platform_prices),
    )
    try:
        selected = select_buff_output_price(market_data=market_data)
    except SteamDTBuffPriceSelectionError as exc:
        return SteamDTPriceSelectionResult(
            market_hash_name=market_data.market_hash_name,
            quote=None,
            selected_platform=None,
            selected_strategy=SCANNER_STRICT_BUFF_SELECTION_STRATEGY,
            reason_codes=[exc.reason.value],
            candidate_decisions=[],
            raw=None,
        )

    quote = SteamDTPriceQuote(
        market_hash_name=selected.market_hash_name,
        price_cny=selected.sell_price_cny,
        source=SCANNER_STRICT_BUFF_SOURCE,
        raw=None,
    )
    return SteamDTPriceSelectionResult(
        market_hash_name=selected.market_hash_name,
        quote=quote,
        selected_platform=selected.platform,
        selected_strategy=SCANNER_STRICT_BUFF_SELECTION_STRATEGY,
        reason_codes=["strict_buff_selected"],
        candidate_decisions=[],
        raw=None,
    )
