from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import NoReturn

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.price_cache import (
    CachedPriceSnapshot,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
)


class SteamDTPriceCacheAdapterErrorReason(StrEnum):
    """Stable classifications for adapter contract failures."""

    INVALID_TYPE = "invalid_type"
    INVALID_VALUE = "invalid_value"
    SNAPSHOT_CONSTRUCTION_FAILED = "snapshot_construction_failed"


class SteamDTPriceCacheAdapterError(ValueError):
    """A non-sensitive SteamDT/cache-model conversion failure."""

    def __init__(
        self,
        *,
        field: str,
        reason: SteamDTPriceCacheAdapterErrorReason,
    ) -> None:
        self.field = field
        self.reason = reason
        super().__init__("SteamDT price-cache adapter rejected invalid data")


def steamdt_platform_price_to_normalized_candidate(
    price: SteamDTPlatformPrice,
) -> NormalizedPriceCandidate:
    """Convert one provider record without retaining mutable raw response data."""

    if not isinstance(price, SteamDTPlatformPrice):
        _raise_adapter_error("platform_price", invalid_type=True)
    _validate_candidate_fields(
        platform=price.platform,
        platform_item_id=price.platform_item_id,
        sell_price_cny=price.sell_price_cny,
        sell_count=price.sell_count,
        bidding_price_cny=price.bidding_price_cny,
        bidding_count=price.bidding_count,
        source_update_time=price.update_time,
        field_prefix="platform_price",
    )
    try:
        return NormalizedPriceCandidate(
            platform=price.platform,
            platform_item_id=price.platform_item_id,
            sell_price_cny=price.sell_price_cny,
            sell_count=price.sell_count,
            bidding_price_cny=price.bidding_price_cny,
            bidding_count=price.bidding_count,
            source_update_time=price.update_time,
        )
    except (TypeError, ValueError):
        raise SteamDTPriceCacheAdapterError(
            field="platform_price",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ) from None


def normalized_candidate_to_steamdt_platform_price(
    candidate: NormalizedPriceCandidate,
) -> SteamDTPlatformPrice:
    """Rebuild selector input with explicitly absent provider raw metadata."""

    if not isinstance(candidate, NormalizedPriceCandidate):
        _raise_adapter_error("candidate", invalid_type=True)
    _validate_candidate_fields(
        platform=candidate.platform,
        platform_item_id=candidate.platform_item_id,
        sell_price_cny=candidate.sell_price_cny,
        sell_count=candidate.sell_count,
        bidding_price_cny=candidate.bidding_price_cny,
        bidding_count=candidate.bidding_count,
        source_update_time=candidate.source_update_time,
        field_prefix="candidate",
    )
    try:
        return SteamDTPlatformPrice(
            platform=candidate.platform,
            platform_item_id=candidate.platform_item_id,
            sell_price_cny=candidate.sell_price_cny,
            sell_count=candidate.sell_count,
            bidding_price_cny=candidate.bidding_price_cny,
            bidding_count=candidate.bidding_count,
            update_time=candidate.source_update_time,
            raw=None,
        )
    except (TypeError, ValueError):
        raise SteamDTPriceCacheAdapterError(
            field="candidate",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ) from None


def steamdt_platform_prices_to_normalized_candidates(
    prices: Sequence[SteamDTPlatformPrice],
) -> tuple[NormalizedPriceCandidate, ...]:
    """Convert records in provider order without sorting or deduplication."""

    if not isinstance(prices, Sequence) or isinstance(prices, (str, bytes)):
        _raise_adapter_error("platform_prices", invalid_type=True)
    candidates: list[NormalizedPriceCandidate] = []
    try:
        for index, price in enumerate(prices):
            try:
                candidates.append(
                    steamdt_platform_price_to_normalized_candidate(price)
                )
            except SteamDTPriceCacheAdapterError as exc:
                raise SteamDTPriceCacheAdapterError(
                    field=f"platform_prices[{index}].{exc.field}",
                    reason=exc.reason,
                ) from None
    except SteamDTPriceCacheAdapterError:
        raise
    except MemoryError:
        raise
    except Exception:
        raise SteamDTPriceCacheAdapterError(
            field="platform_prices",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ) from None
    return tuple(candidates)


def normalized_candidates_to_steamdt_platform_prices(
    candidates: Sequence[NormalizedPriceCandidate],
) -> list[SteamDTPlatformPrice]:
    """Rebuild selector records in cached order without deduplication."""

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        _raise_adapter_error("candidates", invalid_type=True)
    prices: list[SteamDTPlatformPrice] = []
    try:
        for index, candidate in enumerate(candidates):
            try:
                prices.append(
                    normalized_candidate_to_steamdt_platform_price(candidate)
                )
            except SteamDTPriceCacheAdapterError as exc:
                raise SteamDTPriceCacheAdapterError(
                    field=f"candidates[{index}].{exc.field}",
                    reason=exc.reason,
                ) from None
    except SteamDTPriceCacheAdapterError:
        raise
    except MemoryError:
        raise
    except Exception:
        raise SteamDTPriceCacheAdapterError(
            field="candidates",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ) from None
    return prices


def build_steamdt_cached_price_snapshot(
    *,
    key: PriceCacheKey,
    candidates: Sequence[NormalizedPriceCandidate],
    observed_at: datetime,
    stored_at: datetime,
    policy: PriceCachePolicy,
) -> CachedPriceSnapshot:
    """Build an immutable snapshot without reading or writing a cache backend."""

    if not isinstance(key, PriceCacheKey):
        _raise_adapter_error("key", invalid_type=True)
    if not isinstance(policy, PriceCachePolicy):
        _raise_adapter_error("policy", invalid_type=True)
    if not isinstance(observed_at, datetime):
        _raise_adapter_error("observed_at", invalid_type=True)
    if not isinstance(stored_at, datetime):
        _raise_adapter_error("stored_at", invalid_type=True)
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        _raise_adapter_error("candidates", invalid_type=True)
    normalized_candidates: list[NormalizedPriceCandidate] = []
    try:
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, NormalizedPriceCandidate):
                _raise_adapter_error(f"candidates[{index}]", invalid_type=True)
            _validate_candidate_fields(
                platform=candidate.platform,
                platform_item_id=candidate.platform_item_id,
                sell_price_cny=candidate.sell_price_cny,
                sell_count=candidate.sell_count,
                bidding_price_cny=candidate.bidding_price_cny,
                bidding_count=candidate.bidding_count,
                source_update_time=candidate.source_update_time,
                field_prefix=f"candidates[{index}]",
            )
            normalized_candidates.append(candidate)
    except SteamDTPriceCacheAdapterError:
        raise
    except MemoryError:
        raise
    except Exception:
        raise SteamDTPriceCacheAdapterError(
            field="candidates",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ) from None
    try:
        snapshot = CachedPriceSnapshot(
            key=key,
            candidates=tuple(normalized_candidates),
            observed_at=observed_at,
            stored_at=stored_at,
            policy=policy,
        )
        _ = snapshot.fresh_until
        _ = snapshot.stale_until
        _ = snapshot.expires_at
        return snapshot
    except (TypeError, ValueError, OverflowError):
        raise SteamDTPriceCacheAdapterError(
            field="snapshot",
            reason=SteamDTPriceCacheAdapterErrorReason.SNAPSHOT_CONSTRUCTION_FAILED,
        ) from None


def _validate_candidate_fields(
    *,
    platform: object,
    platform_item_id: object,
    sell_price_cny: object,
    sell_count: object,
    bidding_price_cny: object,
    bidding_count: object,
    source_update_time: object,
    field_prefix: str,
) -> None:
    if not isinstance(platform, str):
        _raise_adapter_error(f"{field_prefix}.platform", invalid_type=True)
    if not platform.strip() or platform != platform.strip():
        _raise_adapter_error(f"{field_prefix}.platform")
    if platform_item_id is not None:
        if not isinstance(platform_item_id, str):
            _raise_adapter_error(
                f"{field_prefix}.platform_item_id",
                invalid_type=True,
            )
        if platform_item_id != platform_item_id.strip():
            _raise_adapter_error(f"{field_prefix}.platform_item_id")
    _validate_price(sell_price_cny, field=f"{field_prefix}.sell_price_cny")
    _validate_price(bidding_price_cny, field=f"{field_prefix}.bidding_price_cny")
    _validate_count(sell_count, field=f"{field_prefix}.sell_count")
    _validate_count(bidding_count, field=f"{field_prefix}.bidding_count")
    if source_update_time is not None and (
        isinstance(source_update_time, bool)
        or not isinstance(source_update_time, (int, str))
    ):
        _raise_adapter_error(f"{field_prefix}.source_update_time", invalid_type=True)


def _validate_price(value: object, *, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        _raise_adapter_error(field, invalid_type=True)
    if not value.is_finite() or value < 0:
        _raise_adapter_error(field)


def _validate_count(value: object, *, field: str) -> None:
    if value is None:
        return
    if type(value) is not int:
        _raise_adapter_error(field, invalid_type=True)
    if value < 0:
        _raise_adapter_error(field)


def _raise_adapter_error(
    field: str,
    *,
    invalid_type: bool = False,
) -> NoReturn:
    reason = (
        SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
        if invalid_type
        else SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE
    )
    raise SteamDTPriceCacheAdapterError(field=field, reason=reason) from None