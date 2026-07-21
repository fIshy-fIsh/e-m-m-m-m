from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.clients.steamdt_client import SteamDTPlatformPrice, SteamDTPriceQuote
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    SteamDTPriceSelectionResult,
    select_steamdt_price_quote,
)
from app.services.price_cache import (
    PriceCacheKey,
    PriceCacheLookup,
    PriceCacheReadPolicy,
    PriceCacheState,
)
from app.services.steamdt_price_cache_adapter import (
    normalized_candidates_to_steamdt_platform_prices,
)


class SteamDTCachedPriceResolutionStatus(StrEnum):
    """Normal outcomes of one read-only cached price resolution."""

    SELECTED = "selected"
    MISS = "miss"
    POLICY_BLOCKED = "policy_blocked"
    EXPIRED = "expired"
    SELECTION_FAILURE = "selection_failure"


class SteamDTCachedPriceResolverError(RuntimeError):
    """The cache or injected selector returned an inconsistent contract result."""


class SteamDTPriceCacheReader(Protocol):
    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        """Read one policy-aware price-cache entry."""


class SteamDTPriceSelector(Protocol):
    def __call__(
        self,
        market_hash_name: str,
        platform_prices: list[SteamDTPlatformPrice],
        *,
        config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
        original_payload: dict[str, Any] | None = None,
    ) -> SteamDTPriceSelectionResult:
        """Select one quote from normalized SteamDT platform records."""


@dataclass(frozen=True)
class SteamDTCachedPriceResolution:
    """One cache lookup plus an optional current-policy selection result."""

    status: SteamDTCachedPriceResolutionStatus
    lookup: PriceCacheLookup
    selection_result: SteamDTPriceSelectionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SteamDTCachedPriceResolutionStatus):
            raise TypeError("status must be a SteamDTCachedPriceResolutionStatus")
        if not isinstance(self.lookup, PriceCacheLookup):
            raise TypeError("lookup must be a PriceCacheLookup")
        selected = self.status == SteamDTCachedPriceResolutionStatus.SELECTED
        selection_failure = (
            self.status == SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE
        )
        if selected and (
            self.selection_result is None or self.selection_result.quote is None
        ):
            raise ValueError("selected resolution requires a selected quote")
        if selection_failure and (
            self.selection_result is None or self.selection_result.quote is not None
        ):
            raise ValueError("selection failure requires a result without a quote")
        if selected and (
            not self.lookup.hit
            or self.lookup.snapshot is None
            or self.lookup.policy_blocked
            or self.lookup.expired
        ):
            raise ValueError("selected resolution requires an allowed cache hit")
        if selection_failure and (
            not self.lookup.hit
            or self.lookup.snapshot is None
            or self.lookup.policy_blocked
            or self.lookup.expired
        ):
            raise ValueError("selection failure requires an allowed cache hit")
        if self.status == SteamDTCachedPriceResolutionStatus.MISS and (
            self.lookup.hit
            or self.lookup.state is not None
            or self.lookup.policy_blocked
            or self.lookup.expired
        ):
            raise ValueError("miss resolution requires a plain cache miss")
        if self.status == SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED and (
            self.lookup.hit
            or not self.lookup.policy_blocked
            or self.lookup.expired
        ):
            raise ValueError("policy-blocked resolution requires a blocked cache lookup")
        if self.status == SteamDTCachedPriceResolutionStatus.EXPIRED and (
            self.lookup.hit
            or not self.lookup.expired
            or self.lookup.policy_blocked
        ):
            raise ValueError("expired resolution requires an expired cache lookup")
        if not selected and not selection_failure and self.selection_result is not None:
            raise ValueError("non-hit cache outcomes cannot contain a selection result")

    @property
    def quote(self) -> SteamDTPriceQuote | None:
        if self.selection_result is None:
            return None
        return self.selection_result.quote

    @property
    def selection_failure_reason_codes(self) -> tuple[str, ...]:
        if self.status != SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE:
            return ()
        assert self.selection_result is not None
        return tuple(self.selection_result.reason_codes)


class SteamDTCachedPriceResolver:
    """Resolve a cached snapshot without live fallback or direct cache writes."""

    def __init__(
        self,
        cache: SteamDTPriceCacheReader,
        *,
        selector: SteamDTPriceSelector = select_steamdt_price_quote,
    ) -> None:
        self._cache = cache
        self._selector = selector

    async def resolve(
        self,
        market_hash_name: str,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
    ) -> SteamDTCachedPriceResolution:
        """Read one snapshot and apply the caller's current selection policy."""

        key = PriceCacheKey(market_hash_name=market_hash_name)
        lookup = await self._cache.get(key, read_policy=read_policy)
        self._validate_lookup(key, lookup, read_policy)

        if lookup.expired:
            return SteamDTCachedPriceResolution(
                status=SteamDTCachedPriceResolutionStatus.EXPIRED,
                lookup=lookup,
            )
        if lookup.policy_blocked:
            return SteamDTCachedPriceResolution(
                status=SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED,
                lookup=lookup,
            )
        if not lookup.hit:
            return SteamDTCachedPriceResolution(
                status=SteamDTCachedPriceResolutionStatus.MISS,
                lookup=lookup,
            )

        snapshot = lookup.snapshot
        if snapshot is None:
            raise SteamDTCachedPriceResolverError(
                "cache hit did not include a price snapshot"
            )
        platform_prices = normalized_candidates_to_steamdt_platform_prices(
            snapshot.candidates
        )
        selection_result = self._selector(
            key.market_hash_name,
            platform_prices,
            config=selection_config,
            avg_price_cny=avg_price_cny,
            original_payload=None,
        )
        if not isinstance(selection_result, SteamDTPriceSelectionResult):
            raise SteamDTCachedPriceResolverError(
                "price selector returned an invalid selection result"
            )
        if selection_result.market_hash_name != key.market_hash_name:
            raise SteamDTCachedPriceResolverError(
                "price selector returned a mismatched market hash name"
            )
        if (
            selection_result.quote is not None
            and selection_result.quote.market_hash_name != key.market_hash_name
        ):
            raise SteamDTCachedPriceResolverError(
                "price selector returned a quote for a different market hash name"
            )
        status = (
            SteamDTCachedPriceResolutionStatus.SELECTED
            if selection_result.quote is not None
            else SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE
        )
        return SteamDTCachedPriceResolution(
            status=status,
            lookup=lookup,
            selection_result=selection_result,
        )

    @staticmethod
    def _validate_lookup(
        key: PriceCacheKey,
        lookup: PriceCacheLookup,
        read_policy: PriceCacheReadPolicy,
    ) -> None:
        if not isinstance(lookup, PriceCacheLookup):
            raise SteamDTCachedPriceResolverError(
                "price cache returned an invalid lookup result"
            )
        if lookup.key != key:
            raise SteamDTCachedPriceResolverError(
                "price cache returned a lookup for a different key"
            )
        if lookup.snapshot is not None and lookup.snapshot.key != key:
            raise SteamDTCachedPriceResolverError(
                "price cache returned a snapshot for a different key"
            )

        if lookup.state is None:
            valid = (
                not lookup.hit
                and lookup.snapshot is None
                and lookup.age is None
                and not lookup.needs_refresh
                and not lookup.policy_blocked
                and not lookup.expired
            )
        elif lookup.state == PriceCacheState.FRESH:
            valid = (
                lookup.hit
                and lookup.snapshot is not None
                and lookup.age is not None
                and not lookup.needs_refresh
                and not lookup.policy_blocked
                and not lookup.expired
            )
        elif lookup.state in {
            PriceCacheState.STALE,
            PriceCacheState.STALE_GRACE,
        }:
            valid = (
                lookup.age is not None
                and lookup.needs_refresh
                and not lookup.expired
                and (
                    (
                        lookup.hit
                        and lookup.snapshot is not None
                        and not lookup.policy_blocked
                    )
                    or (
                        not lookup.hit
                        and lookup.snapshot is None
                        and lookup.policy_blocked
                    )
                )
            )
        elif lookup.state == PriceCacheState.EXPIRED:
            valid = (
                not lookup.hit
                and lookup.snapshot is None
                and lookup.age is not None
                and lookup.needs_refresh
                and not lookup.policy_blocked
                and lookup.expired
            )
        else:
            valid = False

        if not valid or (
            lookup.age is not None and lookup.age < timedelta(0)
        ):
            raise SteamDTCachedPriceResolverError(
                "price cache returned an inconsistent lookup result"
            )
        if (
            lookup.snapshot is not None
            and lookup.age is not None
            and not SteamDTCachedPriceResolver._state_matches_age(
                lookup.state,
                lookup.snapshot,
                lookup.age,
            )
        ):
            raise SteamDTCachedPriceResolverError(
                "price cache lookup state does not match the snapshot age"
            )
        if (
            lookup.state == PriceCacheState.STALE
            and lookup.policy_blocked
            and read_policy
            in {
                PriceCacheReadPolicy.ALLOW_STALE,
                PriceCacheReadPolicy.ALLOW_STALE_GRACE,
            }
        ):
            raise SteamDTCachedPriceResolverError(
                "price cache blocked stale data allowed by the read policy"
            )
        if (
            lookup.state == PriceCacheState.STALE_GRACE
            and lookup.policy_blocked
            and read_policy == PriceCacheReadPolicy.ALLOW_STALE_GRACE
        ):
            raise SteamDTCachedPriceResolverError(
                "price cache blocked stale-grace data allowed by the read policy"
            )
        if lookup.hit and lookup.state == PriceCacheState.STALE and read_policy not in {
            PriceCacheReadPolicy.ALLOW_STALE,
            PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        }:
            raise SteamDTCachedPriceResolverError(
                "price cache returned a stale hit blocked by the read policy"
            )
        if (
            lookup.hit
            and lookup.state == PriceCacheState.STALE_GRACE
            and read_policy != PriceCacheReadPolicy.ALLOW_STALE_GRACE
        ):
            raise SteamDTCachedPriceResolverError(
                "price cache returned a stale-grace hit blocked by the read policy"
            )

    @staticmethod
    def _state_matches_age(
        state: PriceCacheState | None,
        snapshot: object,
        age: timedelta,
    ) -> bool:
        from app.services.price_cache import CachedPriceSnapshot

        if not isinstance(snapshot, CachedPriceSnapshot):
            return False
        if state == PriceCacheState.FRESH:
            return age < snapshot.policy.fresh_ttl
        if state == PriceCacheState.STALE:
            return (
                snapshot.policy.fresh_ttl
                <= age
                < snapshot.policy.fresh_ttl + snapshot.policy.stale_ttl
            )
        if state == PriceCacheState.STALE_GRACE:
            return (
                snapshot.policy.fresh_ttl + snapshot.policy.stale_ttl
                <= age
                < snapshot.policy.fresh_ttl
                + snapshot.policy.stale_ttl
                + snapshot.policy.stale_grace_ttl
            )
        return False