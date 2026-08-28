from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.clients.buff_anonymous_listing_client import (
    BuffAnonymousListingPayloadClient,
)

_FIXED_ERROR = "invalid anonymous BUFF listing provider contract"
_ALLOWED_REASONS = frozenset(
    {
        "invalid_goods_id",
        "response_not_json",
        "response_schema_invalid",
        "anonymous_access_unavailable",
        "items_missing",
        "listing_id_invalid",
        "price_invalid",
        "paintwear_invalid",
        "asset_id_invalid",
        "paintseed_invalid",
        "request_failed",
    }
)
_MISSING = object()

__all__ = (
    "BuffListing",
    "BuffListingProviderError",
    "parse_buff_listing_response",
    "BuffListingProvider",
)


class BuffListingProviderError(ValueError):
    """A provider input or response violated the fixed listing contract."""

    def __init__(self, *, reason: str, item_index: int | None = None) -> None:
        if reason not in _ALLOWED_REASONS:
            raise ValueError("unsupported provider error reason")
        if item_index is not None and (
            type(item_index) is not int or item_index < 0
        ):
            raise ValueError("item_index must be a nonnegative integer")
        super().__init__(_FIXED_ERROR)
        self.reason = reason
        self.item_index = item_index


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListing:
    """One normalized listing from the anonymous BUFF compatibility source."""

    listing_id: str
    goods_id: str
    market_hash_name: str | None
    price_cny: Decimal
    paintwear: Decimal
    asset_id: str
    paintseed: int | None
    source: str = "buff"

    def __post_init__(self) -> None:
        failed = False
        market_name = self.market_hash_name
        try:
            _exact_canonical_string(self.listing_id)
            _exact_canonical_string(self.goods_id)
            if market_name is not None:
                _exact_canonical_string(market_name)
            _validate_positive_decimal(self.price_cny)
            _validate_paintwear(self.paintwear)
            _exact_canonical_string(self.asset_id)
            _validate_paintseed(self.paintseed)
            if self.source != "buff":
                raise ValueError
        except MemoryError:
            raise
        except Exception:
            failed = True
        if failed:
            raise BuffListingProviderError(reason="response_schema_invalid")


class BuffListingProvider:
    """Borrow one client and return one atomically parsed listing page."""

    def __init__(self, client: BuffAnonymousListingPayloadClient) -> None:
        if not hasattr(client, "fetch_sell_order_payload"):
            raise BuffListingProviderError(reason="request_failed")
        self._client = client

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        canonical_goods_id = _normalize_provider_goods_id(goods_id)
        failed = False
        payload: bytes | None = None
        try:
            payload = await self._client.fetch_sell_order_payload(canonical_goods_id)
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            failed = True
        if failed or payload is None:
            raise BuffListingProviderError(reason="request_failed")
        return parse_buff_listing_response(payload, goods_id=canonical_goods_id)


def parse_buff_listing_response(
    payload: bytes,
    *,
    goods_id: str,
) -> list[BuffListing]:
    """Parse a complete anonymous response atomically into ordered listings."""

    canonical_goods_id = _validate_exact_goods_id(goods_id)
    if type(payload) is not bytes:
        raise BuffListingProviderError(reason="response_not_json")
    failed = False
    value: object = None
    try:
        value = json.loads(
            payload,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_build_unique_object,
        )
    except MemoryError:
        raise
    except Exception:
        failed = True
    if failed:
        raise BuffListingProviderError(reason="response_not_json")

    if type(value) is not dict:
        raise BuffListingProviderError(reason="response_schema_invalid")
    if value.get("code") != "OK":
        raise BuffListingProviderError(reason="anonymous_access_unavailable")
    data = value.get("data", _MISSING)
    if type(data) is not dict:
        raise BuffListingProviderError(reason="response_schema_invalid")
    items = data.get("items", _MISSING)
    if type(items) is not list:
        raise BuffListingProviderError(reason="items_missing")

    listings: list[BuffListing] = []
    for index, item in enumerate(items):
        listings.append(
            _parse_item(
                item,
                goods_id=canonical_goods_id,
                item_index=index,
            )
        )
    return listings


def _parse_item(
    value: object,
    *,
    goods_id: str,
    item_index: int,
) -> BuffListing:
    if type(value) is not dict:
        raise BuffListingProviderError(
            reason="response_schema_invalid",
            item_index=item_index,
        )
    listing_id = _parse_required_string(
        value.get("id", _MISSING),
        reason="listing_id_invalid",
        item_index=item_index,
    )
    price = _parse_decimal(value.get("price", _MISSING))
    if price is None or price <= 0:
        raise BuffListingProviderError(
            reason="price_invalid",
            item_index=item_index,
        )
    asset_info = value.get("asset_info", _MISSING)
    if type(asset_info) is not dict:
        raise BuffListingProviderError(
            reason="paintwear_invalid",
            item_index=item_index,
        )
    paintwear = _parse_decimal(asset_info.get("paintwear", _MISSING))
    if paintwear is None or not Decimal("0") <= paintwear <= Decimal("1"):
        raise BuffListingProviderError(
            reason="paintwear_invalid",
            item_index=item_index,
        )
    asset_id = _parse_required_string(
        asset_info.get("assetid", _MISSING),
        reason="asset_id_invalid",
        item_index=item_index,
    )
    paintseed_value = asset_info.get("paintseed", _MISSING)
    if paintseed_value is _MISSING or paintseed_value is None:
        paintseed = None
    elif type(paintseed_value) is int and paintseed_value >= 0:
        paintseed = paintseed_value
    else:
        raise BuffListingProviderError(
            reason="paintseed_invalid",
            item_index=item_index,
        )
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=None,
        price_cny=price,
        paintwear=paintwear,
        asset_id=asset_id,
        paintseed=paintseed,
        source="buff",
    )


def _normalize_provider_goods_id(value: object) -> str:
    failed = False
    canonical = ""
    try:
        canonical = _canonical_string(value)
    except MemoryError:
        raise
    except Exception:
        failed = True
    if failed:
        raise BuffListingProviderError(reason="invalid_goods_id")
    return canonical


def _validate_exact_goods_id(value: object) -> str:
    failed = False
    try:
        canonical = _exact_canonical_string(value)
    except MemoryError:
        raise
    except Exception:
        failed = True
        canonical = ""
    if failed:
        raise BuffListingProviderError(reason="invalid_goods_id")
    return canonical


def _canonical_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError
    canonical = value.strip()
    if not canonical:
        raise ValueError
    return canonical


def _exact_canonical_string(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError
    return value


def _parse_required_string(
    value: object,
    *,
    reason: str,
    item_index: int,
) -> str:
    failed = False
    canonical = ""
    try:
        canonical = _exact_canonical_string(value)
    except MemoryError:
        raise
    except Exception:
        failed = True
    if failed:
        raise BuffListingProviderError(
            reason=reason,
            item_index=item_index,
        )
    return canonical


def _parse_decimal(value: object) -> Decimal | None:
    try:
        if type(value) is str:
            if not value or value != value.strip():
                return None
            parsed = Decimal(value)
        elif type(value) is Decimal:
            parsed = value
        elif type(value) is int:
            parsed = Decimal(value)
        else:
            return None
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _validate_positive_decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise ValueError


def _validate_paintwear(value: object) -> None:
    if (
        type(value) is not Decimal
        or not value.is_finite()
        or not Decimal("0") <= value <= Decimal("1")
    ):
        raise ValueError


def _validate_paintseed(value: object) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError


def _reject_json_constant(_value: str) -> object:
    raise ValueError


def _build_unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result
