from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.price_cache import (
    CachedPriceSnapshot,
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheWriteResult,
    UtcClock,
)
from app.services.steamdt_price_cache_adapter import (
    build_steamdt_cached_price_snapshot,
    steamdt_platform_prices_to_normalized_candidates,
)


@dataclass(frozen=True)
class SteamDTFetchedPriceSnapshot:
    """One source-owned selector-before SteamDT price observation."""

    market_hash_name: str
    source: str
    candidates: tuple[SteamDTPlatformPrice, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        market_hash_name = _canonical_identity(
            self.market_hash_name,
            field_name="market_hash_name",
        )
        source = _canonical_identity(self.source, field_name="source")
        observed_at = _aware_utc(self.observed_at, field_name="observed_at")
        if not isinstance(self.candidates, Sequence) or isinstance(
            self.candidates,
            (str, bytes),
        ):
            raise TypeError("candidates must be a sequence of SteamDTPlatformPrice")
        candidates: list[SteamDTPlatformPrice] = []
        for candidate in self.candidates:
            if not isinstance(candidate, SteamDTPlatformPrice):
                raise TypeError(
                    "candidates must contain only SteamDTPlatformPrice values"
                )
            candidates.append(_clone_without_raw(candidate))
        object.__setattr__(self, "market_hash_name", market_hash_name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "candidates", tuple(candidates))
        object.__setattr__(self, "observed_at", observed_at)


class SteamDTPriceSnapshotSource(Protocol):
    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        """Fetch one complete selector-before observation for a canonical item name."""


class SteamDTPriceCacheWriter(Protocol):
    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        """Submit one immutable observation to the configured cache backend."""


class SteamDTPriceRefreshStatus(StrEnum):
    NO_CANDIDATES = "no_candidates"
    CACHE_PUT_COMPLETED = "cache_put_completed"


@dataclass(frozen=True)
class SteamDTPriceRefreshResult:
    """One source fetch and optional cache-put arbitration outcome."""

    status: SteamDTPriceRefreshStatus
    key: PriceCacheKey
    observed_at: datetime
    candidate_count: int
    write_result: PriceCacheWriteResult | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SteamDTPriceRefreshStatus):
            raise TypeError("status must be a SteamDTPriceRefreshStatus")
        if not isinstance(self.key, PriceCacheKey):
            raise TypeError("key must be a PriceCacheKey")
        observed_at = _aware_utc(self.observed_at, field_name="observed_at")
        if type(self.candidate_count) is not int:
            raise TypeError("candidate_count must be an int")
        if self.candidate_count < 0:
            raise ValueError("candidate_count must be greater than or equal to 0")
        if self.status == SteamDTPriceRefreshStatus.NO_CANDIDATES:
            if self.candidate_count != 0 or self.write_result is not None:
                raise ValueError(
                    "no-candidates result requires zero candidates and no write result"
                )
        elif (
            self.candidate_count <= 0
            or not isinstance(self.write_result, PriceCacheWriteResult)
        ):
            raise ValueError(
                "completed cache put requires candidates and a cache write result"
            )
        object.__setattr__(self, "observed_at", observed_at)


class SteamDTPriceRefreshValidationError(RuntimeError):
    """An injected source or cache writer violated the refresh contract."""


class SteamDTPriceRefreshService:
    """Fetch and write one pre-selection price snapshot without read or fallback."""

    def __init__(
        self,
        source: SteamDTPriceSnapshotSource,
        cache: SteamDTPriceCacheWriter,
        *,
        clock: UtcClock | None = None,
    ) -> None:
        self._source = source
        self._cache = cache
        self._clock = clock or _utc_now

    async def refresh_one(
        self,
        market_hash_name: str,
        policy: PriceCachePolicy,
    ) -> SteamDTPriceRefreshResult:
        """Fetch one observation and submit it once to the cache writer."""

        key = PriceCacheKey(market_hash_name=market_hash_name)
        fetched = await self._source.fetch_price_snapshot(key.market_hash_name)
        if not isinstance(fetched, SteamDTFetchedPriceSnapshot):
            raise SteamDTPriceRefreshValidationError(
                "SteamDT price snapshot source returned an invalid result"
            )
        if fetched.market_hash_name != key.market_hash_name:
            raise SteamDTPriceRefreshValidationError(
                "SteamDT price snapshot source returned a different item"
            )
        if fetched.source != key.source:
            raise SteamDTPriceRefreshValidationError(
                "SteamDT price snapshot source returned a different source"
            )

        candidate_count = len(fetched.candidates)
        if candidate_count == 0:
            return SteamDTPriceRefreshResult(
                status=SteamDTPriceRefreshStatus.NO_CANDIDATES,
                key=key,
                observed_at=fetched.observed_at,
                candidate_count=0,
                write_result=None,
            )

        candidates = steamdt_platform_prices_to_normalized_candidates(
            fetched.candidates
        )
        provisional_stored_at = self._clock()
        if (
            isinstance(provisional_stored_at, datetime)
            and provisional_stored_at.tzinfo is not None
            and provisional_stored_at.utcoffset() is not None
            and provisional_stored_at.astimezone(UTC) < fetched.observed_at
        ):
            provisional_stored_at = fetched.observed_at
        snapshot = build_steamdt_cached_price_snapshot(
            key=key,
            candidates=candidates,
            observed_at=fetched.observed_at,
            stored_at=provisional_stored_at,
            policy=policy,
        )
        write_result = await self._cache.put(snapshot)
        if not isinstance(write_result, PriceCacheWriteResult):
            raise SteamDTPriceRefreshValidationError(
                "SteamDT price cache writer returned an invalid result"
            )
        return SteamDTPriceRefreshResult(
            status=SteamDTPriceRefreshStatus.CACHE_PUT_COMPLETED,
            key=key,
            observed_at=fetched.observed_at,
            candidate_count=candidate_count,
            write_result=write_result,
        )


def _clone_without_raw(candidate: SteamDTPlatformPrice) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=candidate.platform,
        platform_item_id=candidate.platform_item_id,
        sell_price_cny=candidate.sell_price_cny,
        sell_count=candidate.sell_count,
        bidding_price_cny=candidate.bidding_price_cny,
        bidding_count=candidate.bidding_count,
        update_time=candidate.update_time,
        raw=None,
    )


def _canonical_identity(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be nonempty without surrounding whitespace")
    return value


def _aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
