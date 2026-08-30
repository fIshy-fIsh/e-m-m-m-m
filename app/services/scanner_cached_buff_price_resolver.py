"""Scanner-owned strict-BUFF composition over the Phase 12D cache reader."""

from __future__ import annotations

from app.services.price_cache import PriceCacheReadPolicy
from app.services.scanner_cached_buff_price_selector import (
    select_scanner_cached_buff_price,
)
from app.services.steamdt_cached_price_resolver import (
    SteamDTCachedPriceResolution,
    SteamDTCachedPriceResolver,
    SteamDTPriceCacheReader,
)

__all__ = ("ScannerCachedBuffPriceResolver",)


class ScannerCachedBuffPriceResolver:
    """Bind scanner cache reads permanently to strict BUFF selection."""

    def __init__(self, cache: SteamDTPriceCacheReader) -> None:
        if cache is None:
            raise TypeError("cache is required")
        self._resolver = SteamDTCachedPriceResolver(
            cache,
            selector=select_scanner_cached_buff_price,
        )

    async def resolve(
        self,
        market_hash_name: str,
    ) -> SteamDTCachedPriceResolution:
        """Resolve one exact name with the scanner's fixed FRESH_ONLY policy."""

        return await self._resolver.resolve(
            market_hash_name,
            read_policy=PriceCacheReadPolicy.FRESH_ONLY,
        )
