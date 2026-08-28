from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.price_cache import UtcClock
from app.services.steamdt_price_refresh_service import SteamDTFetchedPriceSnapshot


class SteamDTSinglePriceCandidateClient(Protocol):
    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        """Fetch one complete selector-before candidate collection."""


class SteamDTSinglePriceSnapshotSource:
    """Adapt the official single-price client into a clocked snapshot source."""

    def __init__(
        self,
        client: SteamDTSinglePriceCandidateClient,
        *,
        clock: UtcClock | None = None,
    ) -> None:
        self._client = client
        self._clock = clock or _utc_now

    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        """Fetch candidates once and timestamp successful parsing completion."""

        if not isinstance(market_hash_name, str):
            raise TypeError("market_hash_name must be a string")
        if not market_hash_name or market_hash_name != market_hash_name.strip():
            raise ValueError(
                "market_hash_name must be nonempty without surrounding whitespace"
            )

        candidates = await self._client.get_price_single_candidates(market_hash_name)
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise TypeError(
                "SteamDT single-price client returned an invalid candidate sequence"
            )
        if any(not isinstance(candidate, SteamDTPlatformPrice) for candidate in candidates):
            raise TypeError(
                "SteamDT single-price client returned an invalid candidate value"
            )

        return SteamDTFetchedPriceSnapshot(
            market_hash_name=market_hash_name,
            source="steamdt",
            candidates=tuple(candidates),
            observed_at=self._clock(),
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)
