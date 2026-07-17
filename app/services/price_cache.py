from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

PRICE_CACHE_SCHEMA_VERSION = 1
DEFAULT_PRICE_CACHE_GAME = "cs2"
DEFAULT_PRICE_CACHE_CURRENCY = "CNY"
DEFAULT_PRICE_CACHE_SOURCE = "steamdt"
DEFAULT_PRICE_CACHE_SNAPSHOT_TYPE = "platform_prices"

UtcClock = Callable[[], datetime]


@dataclass(frozen=True)
class PriceCacheKey:
    """Stable identity for one provider-normalized, pre-selection price snapshot."""

    market_hash_name: str
    game: str = DEFAULT_PRICE_CACHE_GAME
    currency: str = DEFAULT_PRICE_CACHE_CURRENCY
    source: str = DEFAULT_PRICE_CACHE_SOURCE
    snapshot_type: str = DEFAULT_PRICE_CACHE_SNAPSHOT_TYPE
    schema_version: int = PRICE_CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("market_hash_name", self.market_hash_name),
            ("game", self.game),
            ("source", self.source),
            ("snapshot_type", self.snapshot_type),
        ):
            normalized = _require_string(value, field_name=name).strip()
            if not normalized:
                raise ValueError(f"{name} cannot be empty")
            object.__setattr__(self, name, normalized)
        currency = _require_string(self.currency, field_name="currency").strip().upper()
        if currency != DEFAULT_PRICE_CACHE_CURRENCY:
            raise ValueError(
                "currency must be CNY while the normalized payload uses CNY price fields"
            )
        object.__setattr__(self, "currency", currency)
        if (
            type(self.schema_version) is not int
            or self.schema_version != PRICE_CACHE_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version must be {PRICE_CACHE_SCHEMA_VERSION}"
            )

    def serialize(self) -> str:
        """Return deterministic JSON that does not depend on Python hashing or repr."""

        return json.dumps(
            {
                "currency": self.currency,
                "game": self.game,
                "market_hash_name": self.market_hash_name,
                "schema_version": self.schema_version,
                "snapshot_type": self.snapshot_type,
                "source": self.source,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def stable_digest(self) -> str:
        """Return a process-independent digest suitable for a future Redis key suffix."""

        return hashlib.sha256(self.serialize().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NormalizedPriceCandidate:
    """Immutable normalized platform record retained before price selection."""

    platform: str
    platform_item_id: str | None = None
    sell_price_cny: Decimal | None = None
    sell_count: int | None = None
    bidding_price_cny: Decimal | None = None
    bidding_count: int | None = None
    source_update_time: int | str | None = None

    def __post_init__(self) -> None:
        platform = _require_string(self.platform, field_name="platform").strip()
        if not platform:
            raise ValueError("platform cannot be empty")
        object.__setattr__(self, "platform", platform)
        if self.platform_item_id is not None:
            platform_item_id = _require_string(
                self.platform_item_id,
                field_name="platform_item_id",
            ).strip()
            object.__setattr__(self, "platform_item_id", platform_item_id)
        _validate_price(self.sell_price_cny, field_name="sell_price_cny")
        _validate_price(self.bidding_price_cny, field_name="bidding_price_cny")
        _validate_count(self.sell_count, field_name="sell_count")
        _validate_count(self.bidding_count, field_name="bidding_count")
        if self.source_update_time is not None and (
            isinstance(self.source_update_time, bool)
            or not isinstance(self.source_update_time, (int, str))
        ):
            raise TypeError("source_update_time must be an int, string, or None")

    def to_serializable(self) -> dict[str, int | str | None]:
        """Return a JSON-ready representation that preserves Decimal precision."""

        return {
            "bidding_count": self.bidding_count,
            "bidding_price_cny": _decimal_to_string(self.bidding_price_cny),
            "platform": self.platform,
            "platform_item_id": self.platform_item_id,
            "sell_count": self.sell_count,
            "sell_price_cny": _decimal_to_string(self.sell_price_cny),
            "source_update_time": self.source_update_time,
        }


@dataclass(frozen=True)
class PriceCachePolicy:
    """Explicit freshness durations for price observations."""

    fresh_ttl: timedelta
    stale_ttl: timedelta = timedelta(0)
    stale_grace_ttl: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        if self.fresh_ttl <= timedelta(0):
            raise ValueError("fresh_ttl must be greater than 0")
        if self.stale_ttl < timedelta(0):
            raise ValueError("stale_ttl must be greater than or equal to 0")
        if self.stale_grace_ttl < timedelta(0):
            raise ValueError("stale_grace_ttl must be greater than or equal to 0")


@dataclass(frozen=True)
class CachedPriceSnapshot:
    """Immutable observation; a cache stamps authoritative storage time on put."""

    key: PriceCacheKey
    candidates: tuple[NormalizedPriceCandidate, ...]
    observed_at: datetime
    stored_at: datetime
    policy: PriceCachePolicy
    schema_version: int = PRICE_CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        observed_at = _normalize_utc(self.observed_at, field_name="observed_at")
        stored_at = _normalize_utc(self.stored_at, field_name="stored_at")
        if observed_at > stored_at:
            raise ValueError("observed_at cannot be later than stored_at")
        if (
            type(self.schema_version) is not int
            or self.schema_version != PRICE_CACHE_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version must be {PRICE_CACHE_SCHEMA_VERSION}"
            )
        if self.schema_version != self.key.schema_version:
            raise ValueError("snapshot schema_version must match cache key schema_version")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "stored_at", stored_at)
        object.__setattr__(self, "candidates", tuple(self.candidates))

    @property
    def fresh_until(self) -> datetime:
        return self.observed_at + self.policy.fresh_ttl

    @property
    def stale_until(self) -> datetime:
        return self.fresh_until + self.policy.stale_ttl

    @property
    def expires_at(self) -> datetime:
        return self.stale_until + self.policy.stale_grace_ttl

    def to_serializable(self) -> dict[str, object]:
        """Return a future-codec boundary with strings for Decimal and UTC datetime."""

        return {
            "candidates": [candidate.to_serializable() for candidate in self.candidates],
            "key": json.loads(self.key.serialize()),
            "observed_at": _format_utc(self.observed_at),
            "policy": {
                "fresh_ttl_seconds": _timedelta_to_decimal_string(
                    self.policy.fresh_ttl
                ),
                "stale_grace_ttl_seconds": _timedelta_to_decimal_string(
                    self.policy.stale_grace_ttl
                ),
                "stale_ttl_seconds": _timedelta_to_decimal_string(
                    self.policy.stale_ttl
                ),
            },
            "schema_version": self.schema_version,
            "stored_at": _format_utc(self.stored_at),
        }


class PriceCacheState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    STALE_GRACE = "stale_grace"
    EXPIRED = "expired"


class PriceCacheReadPolicy(StrEnum):
    FRESH_ONLY = "fresh_only"
    ALLOW_STALE = "allow_stale"
    ALLOW_STALE_GRACE = "allow_stale_grace"


class PriceCacheWriteResult(StrEnum):
    CREATED = "created"
    REPLACED = "replaced"
    IGNORED_OLDER = "ignored_older"
    UNCHANGED_EQUAL = "unchanged_equal"


@dataclass(frozen=True)
class PriceCacheLookup:
    """Policy-aware cache lookup; misses never raise an exception."""

    key: PriceCacheKey
    hit: bool
    state: PriceCacheState | None
    snapshot: CachedPriceSnapshot | None
    age: timedelta | None
    needs_refresh: bool
    policy_blocked: bool
    expired: bool

    @classmethod
    def missing(cls, key: PriceCacheKey) -> PriceCacheLookup:
        return cls(
            key=key,
            hit=False,
            state=None,
            snapshot=None,
            age=None,
            needs_refresh=False,
            policy_blocked=False,
            expired=False,
        )


class PriceCache(Protocol):
    """Async price-cache boundary for in-memory and future shared backends."""

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        """Read one key according to an explicit availability policy."""

    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        """Store an observation; the implementation owns final storage time."""

    async def delete(self, key: PriceCacheKey) -> bool:
        """Delete one key and return whether it existed."""

    async def clear(self) -> None:
        """Clear only this cache instance."""

    async def purge_expired(self) -> int:
        """Delete expired entries and return the number removed."""


class InMemoryPriceCache:
    """Concurrency-safe instance-local implementation with an injectable UTC clock."""

    def __init__(self, *, clock: UtcClock | None = None) -> None:
        self._clock = clock or _utc_now
        self._entries: dict[PriceCacheKey, CachedPriceSnapshot] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        async with self._lock:
            now = self._read_clock()
            snapshot = self._entries.get(key)
            if snapshot is None:
                return PriceCacheLookup.missing(key)

            state = _state_at(snapshot, now)
            age = now - snapshot.observed_at
            if state == PriceCacheState.EXPIRED:
                del self._entries[key]
                return PriceCacheLookup(
                    key=key,
                    hit=False,
                    state=state,
                    snapshot=None,
                    age=age,
                    needs_refresh=True,
                    policy_blocked=False,
                    expired=True,
                )

            allowed = _state_is_allowed(state, read_policy)
            return PriceCacheLookup(
                key=key,
                hit=allowed,
                state=state,
                snapshot=snapshot if allowed else None,
                age=age,
                needs_refresh=state != PriceCacheState.FRESH,
                policy_blocked=not allowed,
                expired=False,
            )

    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        """Store a snapshot using this cache's clock as the storage-time authority."""

        async with self._lock:
            stored_at = self._read_clock()
            if snapshot.observed_at > stored_at:
                raise ValueError("observed_at cannot be later than cache storage time")
            stored_snapshot = replace(snapshot, stored_at=stored_at)
            existing = self._entries.get(stored_snapshot.key)
            if existing is None:
                self._entries[stored_snapshot.key] = stored_snapshot
                return PriceCacheWriteResult.CREATED
            if stored_snapshot.observed_at > existing.observed_at:
                self._entries[stored_snapshot.key] = stored_snapshot
                return PriceCacheWriteResult.REPLACED
            if stored_snapshot.observed_at < existing.observed_at:
                return PriceCacheWriteResult.IGNORED_OLDER
            return PriceCacheWriteResult.UNCHANGED_EQUAL

    async def delete(self, key: PriceCacheKey) -> bool:
        async with self._lock:
            return self._entries.pop(key, None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()

    async def purge_expired(self) -> int:
        async with self._lock:
            now = self._read_clock()
            expired_keys = [
                key
                for key, snapshot in self._entries.items()
                if _state_at(snapshot, now) == PriceCacheState.EXPIRED
            ]
            for key in expired_keys:
                del self._entries[key]
            return len(expired_keys)

    def _read_clock(self) -> datetime:
        return _normalize_utc(self._clock(), field_name="clock result")


def _state_at(snapshot: CachedPriceSnapshot, now: datetime) -> PriceCacheState:
    if now < snapshot.observed_at:
        raise ValueError("cache clock cannot be earlier than stored observation")
    if now < snapshot.fresh_until:
        return PriceCacheState.FRESH
    if now < snapshot.stale_until:
        return PriceCacheState.STALE
    if now < snapshot.expires_at:
        return PriceCacheState.STALE_GRACE
    return PriceCacheState.EXPIRED


def _state_is_allowed(
    state: PriceCacheState,
    read_policy: PriceCacheReadPolicy,
) -> bool:
    if state == PriceCacheState.FRESH:
        return True
    if state == PriceCacheState.STALE:
        return read_policy in {
            PriceCacheReadPolicy.ALLOW_STALE,
            PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        }
    if state == PriceCacheState.STALE_GRACE:
        return read_policy == PriceCacheReadPolicy.ALLOW_STALE_GRACE
    return False


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _validate_price(value: Decimal | None, *, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal or None")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")


def _validate_count(value: int | None, *, field_name: str) -> None:
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int or None")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal_to_string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _timedelta_to_decimal_string(value: timedelta) -> str:
    microseconds = (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )
    return str(Decimal(microseconds) / Decimal(1_000_000))
