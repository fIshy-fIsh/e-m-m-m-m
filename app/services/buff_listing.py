from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

StickerMetadata = tuple[tuple[str, str], ...]


class BuffListingValidationError(ValueError):
    """A BUFF listing value violated the safe input contract."""

    def __init__(self, *, field: str) -> None:
        super().__init__(f"invalid BUFF listing field: {field}")
        self.field = field


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingObservation:
    """Provider observation before it crosses the normalized solver boundary."""

    listing_id: str
    market_hash_name: str
    price_cny: Decimal
    quantity: int
    float_value: Decimal | None = None
    wear_name: str | None = None
    paint_seed: int | None = None
    sticker_metadata: Sequence[tuple[str, str]] | None = None
    observed_at: datetime
    goods_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "listing_id",
            _normalize_required_string(self.listing_id, field="listing_id"),
        )
        object.__setattr__(
            self,
            "market_hash_name",
            _normalize_required_string(
                self.market_hash_name,
                field="market_hash_name",
            ),
        )
        _validate_nonnegative_decimal(self.price_cny, field="price_cny")
        _validate_nonnegative_exact_int(self.quantity, field="quantity")
        _validate_float_value(self.float_value)
        object.__setattr__(
            self,
            "wear_name",
            _normalize_optional_string(self.wear_name, field="wear_name"),
        )
        _validate_optional_nonnegative_exact_int(
            self.paint_seed,
            field="paint_seed",
        )
        object.__setattr__(
            self,
            "sticker_metadata",
            _normalize_sticker_metadata(self.sticker_metadata),
        )
        object.__setattr__(
            self,
            "observed_at",
            _normalize_utc(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "goods_id",
            _normalize_optional_identifier(self.goods_id, field="goods_id"),
        )


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffTradableCandidate:
    """Validated listing data safe to pass into later solver logic."""

    listing_id: str
    market_hash_name: str
    buy_price_cny: Decimal
    available_quantity: int
    float_value: Decimal | None
    wear_name: str | None
    paint_seed: int | None
    observed_at: datetime
    goods_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "listing_id",
            _normalize_required_string(self.listing_id, field="listing_id"),
        )
        object.__setattr__(
            self,
            "market_hash_name",
            _normalize_required_string(
                self.market_hash_name,
                field="market_hash_name",
            ),
        )
        _validate_nonnegative_decimal(self.buy_price_cny, field="buy_price_cny")
        _validate_nonnegative_exact_int(
            self.available_quantity,
            field="available_quantity",
        )
        _validate_float_value(self.float_value)
        object.__setattr__(
            self,
            "wear_name",
            _normalize_optional_string(self.wear_name, field="wear_name"),
        )
        _validate_optional_nonnegative_exact_int(
            self.paint_seed,
            field="paint_seed",
        )
        object.__setattr__(
            self,
            "observed_at",
            _normalize_utc(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "goods_id",
            _normalize_optional_identifier(self.goods_id, field="goods_id"),
        )


class BuffListingSource(Protocol):
    """Read-only provider boundary for BUFF listing observations."""

    async def fetch_listings(
        self,
        market_hash_name: str,
    ) -> Sequence[BuffListingObservation]:
        """Fetch observations without defining transport or authentication."""


def normalize_buff_listing(
    observation: BuffListingObservation,
) -> BuffTradableCandidate:
    """Validate and normalize one observation without applying business policy."""

    if not isinstance(observation, BuffListingObservation):
        raise BuffListingValidationError(field="observation")

    validated = BuffListingObservation(
        listing_id=observation.listing_id,
        market_hash_name=observation.market_hash_name,
        price_cny=observation.price_cny,
        quantity=observation.quantity,
        float_value=observation.float_value,
        wear_name=observation.wear_name,
        paint_seed=observation.paint_seed,
        sticker_metadata=observation.sticker_metadata,
        observed_at=observation.observed_at,
        goods_id=observation.goods_id,
    )
    return BuffTradableCandidate(
        listing_id=validated.listing_id,
        market_hash_name=validated.market_hash_name,
        buy_price_cny=validated.price_cny,
        available_quantity=validated.quantity,
        float_value=validated.float_value,
        wear_name=validated.wear_name,
        paint_seed=validated.paint_seed,
        observed_at=validated.observed_at,
        goods_id=validated.goods_id,
    )


def _normalize_required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise BuffListingValidationError(field=field)
    try:
        normalized = value.strip()
    except Exception:
        raise BuffListingValidationError(field=field) from None
    if not normalized:
        raise BuffListingValidationError(field=field)
    return normalized


def _normalize_optional_identifier(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BuffListingValidationError(field=field)
    try:
        normalized = str.strip(str.__str__(value))
    except Exception:
        raise BuffListingValidationError(field=field) from None
    if not normalized:
        raise BuffListingValidationError(field=field)
    return normalized


def _normalize_optional_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BuffListingValidationError(field=field)
    try:
        normalized = value.strip()
    except Exception:
        raise BuffListingValidationError(field=field) from None
    return normalized or None


def _validate_nonnegative_decimal(value: object, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise BuffListingValidationError(field=field)
    try:
        valid = value.is_finite() and value >= 0
    except Exception:
        raise BuffListingValidationError(field=field) from None
    if not valid:
        raise BuffListingValidationError(field=field)


def _validate_float_value(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise BuffListingValidationError(field="float_value")
    try:
        valid = value.is_finite() and Decimal(0) <= value <= Decimal(1)
    except Exception:
        raise BuffListingValidationError(field="float_value") from None
    if not valid:
        raise BuffListingValidationError(field="float_value")


def _validate_nonnegative_exact_int(value: object, *, field: str) -> None:
    if type(value) is not int or value < 0:
        raise BuffListingValidationError(field=field)


def _validate_optional_nonnegative_exact_int(
    value: object,
    *,
    field: str,
) -> None:
    if value is not None:
        _validate_nonnegative_exact_int(value, field=field)


def _normalize_sticker_metadata(
    value: object,
) -> StickerMetadata | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BuffListingValidationError(field="sticker_metadata")

    normalized: list[tuple[str, str]] = []
    try:
        for pair in value:
            if (
                not isinstance(pair, Sequence)
                or isinstance(pair, (str, bytes))
                or len(pair) != 2
            ):
                raise BuffListingValidationError(field="sticker_metadata")
            key = _normalize_required_string(pair[0], field="sticker_metadata")
            item_value = _normalize_required_string(
                pair[1],
                field="sticker_metadata",
            )
            normalized.append((key, item_value))
    except BuffListingValidationError:
        raise
    except Exception:
        raise BuffListingValidationError(field="sticker_metadata") from None
    return tuple(normalized)


def _normalize_utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise BuffListingValidationError(field=field)
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise BuffListingValidationError(field=field)
        return value.astimezone(UTC)
    except BuffListingValidationError:
        raise
    except Exception:
        raise BuffListingValidationError(field=field) from None
