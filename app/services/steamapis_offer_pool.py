from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.market_scan_service import CandidateListing
from app.services.steamapis_candidate_adapter import (
    adapt_steamapis_listing_to_candidate,
)
from app.services.steamapis_listing import SteamApisListingObservation

_FIXED_ERROR_MESSAGE = "invalid SteamApis offer pool contract"

__all__ = (
    "SteamApisOfferPoolError",
    "SteamApisOfferPoolSnapshot",
    "SteamApisOfferPool",
)


class SteamApisOfferPoolError(ValueError):
    """A value or operation violated the safe offer-pool contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisOfferPoolSnapshot:
    """Immutable deterministic view of the live observation pool."""

    observations: tuple[SteamApisListingObservation, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.observations) is not tuple or any(
                type(observation) is not SteamApisListingObservation
                for observation in self.observations
            ):
                raise SteamApisOfferPoolError
            object.__setattr__(
                self,
                "observations",
                tuple(sorted(self.observations, key=_snapshot_sort_key)),
            )
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None


class SteamApisOfferPool:
    """Bounded instance-local store of SteamApis offer observations."""

    def __init__(
        self,
        *,
        max_size: int,
        ttl: timedelta,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        try:
            if type(max_size) is not int or max_size <= 0:
                raise SteamApisOfferPoolError
            if type(ttl) is not timedelta or ttl <= timedelta(0):
                raise SteamApisOfferPoolError
            if not callable(now):
                raise SteamApisOfferPoolError
            _normalize_clock(now())
            self._max_size = max_size
            self._ttl = ttl
            self._now = now
            self._observations: dict[str, SteamApisListingObservation] = {}
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def ingest(self, observation: SteamApisListingObservation) -> None:
        """Ingest one Added or Updated observation by message time."""

        try:
            validated = _reconstruct_observation(observation)
            operation_now = self._read_clock()
            self._evict_expired(operation_now)
            if _is_expired(validated, now=operation_now, ttl=self._ttl):
                return

            stored = self._observations.get(validated.source_offer_id)
            if stored is not None:
                if validated.message_timestamp < stored.message_timestamp:
                    return
                if validated.message_timestamp == stored.message_timestamp:
                    if validated == stored:
                        return
                    raise SteamApisOfferPoolError

            self._observations[validated.source_offer_id] = validated
            self._enforce_capacity()
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def snapshot(self) -> SteamApisOfferPoolSnapshot:
        """Return a stable immutable snapshot after local TTL eviction."""

        try:
            operation_now = self._read_clock()
            self._evict_expired(operation_now)
            return SteamApisOfferPoolSnapshot(
                observations=tuple(self._observations.values()),
            )
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def get_observation(
        self,
        source_offer_id: str,
    ) -> SteamApisListingObservation | None:
        """Look up current source provenance without external activity."""

        try:
            canonical_id = _validate_source_offer_id(source_offer_id)
            operation_now = self._read_clock()
            self._evict_expired(operation_now)
            return self._observations.get(canonical_id)
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def get_purchase_link(self, source_offer_id: str) -> str | None:
        """Return the retained opaque manual link for one current offer."""

        try:
            canonical_id = _validate_source_offer_id(source_offer_id)
            operation_now = self._read_clock()
            self._evict_expired(operation_now)
            observation = self._observations.get(canonical_id)
            return None if observation is None else observation.purchase_link
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def snapshot_candidates(self) -> tuple[CandidateListing, ...]:
        """Project one current snapshot through the existing Step 2B adapter."""

        try:
            snapshot = self.snapshot()
            return tuple(
                adapt_steamapis_listing_to_candidate(observation)
                for observation in snapshot.observations
            )
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferPoolError from None

    def _read_clock(self) -> datetime:
        return _normalize_clock(self._now())

    def _evict_expired(self, operation_now: datetime) -> None:
        expired_ids = tuple(
            source_offer_id
            for source_offer_id, observation in self._observations.items()
            if _is_expired(observation, now=operation_now, ttl=self._ttl)
        )
        for source_offer_id in expired_ids:
            del self._observations[source_offer_id]

    def _enforce_capacity(self) -> None:
        while len(self._observations) > self._max_size:
            source_offer_id = min(
                self._observations,
                key=lambda key: (
                    self._observations[key].message_timestamp,
                    key,
                ),
            )
            del self._observations[source_offer_id]


def _normalize_clock(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SteamApisOfferPoolError
    return value.astimezone(UTC)


def _reconstruct_observation(value: object) -> SteamApisListingObservation:
    if type(value) is not SteamApisListingObservation:
        raise SteamApisOfferPoolError
    return SteamApisListingObservation(
        source_offer_id=value.source_offer_id,
        event_type=value.event_type,
        marketplace=value.marketplace,
        game=value.game,
        market_hash_name=value.market_hash_name,
        purchase_link=value.purchase_link,
        inspect_link=value.inspect_link,
        price_cny=value.price_cny,
        float_value=value.float_value,
        paint_index=value.paint_index,
        paint_seed=value.paint_seed,
        days_trade_locked=value.days_trade_locked,
        found_at=value.found_at,
        message_timestamp=value.message_timestamp,
        stickers=value.stickers,
    )


def _validate_source_offer_id(value: object) -> str:
    if type(value) is not str:
        raise SteamApisOfferPoolError
    source_offer_id = str.__str__(value)
    if len(source_offer_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_offer_id
    ):
        raise SteamApisOfferPoolError
    return source_offer_id


def _is_expired(
    observation: SteamApisListingObservation,
    *,
    now: datetime,
    ttl: timedelta,
) -> bool:
    return now - observation.message_timestamp >= ttl


def _snapshot_sort_key(
    observation: SteamApisListingObservation,
) -> tuple[str, Decimal, Decimal, datetime, str]:
    return (
        observation.market_hash_name,
        observation.price_cny,
        observation.float_value,
        observation.message_timestamp,
        observation.source_offer_id,
    )
