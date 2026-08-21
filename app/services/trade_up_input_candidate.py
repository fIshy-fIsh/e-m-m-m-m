from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_FIXED_ERROR = "invalid trade-up input candidate contract"
_ALLOWED_FIELDS = frozenset(
    {
        "listing_id",
        "goods_id",
        "market_hash_name",
        "price_cny",
        "paintwear",
        "asset_id",
        "source",
    }
)

__all__ = (
    "TradeUpInputCandidateValidationError",
    "TradeUpInputCandidate",
)


class TradeUpInputCandidateValidationError(ValueError):
    """A trade-up input candidate value violated the fixed boundary contract."""

    def __init__(self, *, field: str) -> None:
        if field not in _ALLOWED_FIELDS:
            raise ValueError("unsupported trade-up input candidate field")
        super().__init__(_FIXED_ERROR)
        self.field = field


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputCandidate:
    """One normalized input element for the future trade-up engine.

    The boundary intentionally accommodates unresolved identity. The
    `market_hash_name` field is left as `None` until a verified
    `market_hash_name <-> BUFF goods_id` source is wired upstream.
    """

    listing_id: str
    goods_id: str
    market_hash_name: str | None
    price_cny: Decimal
    paintwear: Decimal
    asset_id: str
    source: str = "buff"

    def __post_init__(self) -> None:
        _validate_exact_string(self.listing_id, field="listing_id")
        _validate_exact_string(self.goods_id, field="goods_id")
        if self.market_hash_name is not None:
            _validate_exact_string(self.market_hash_name, field="market_hash_name")
        _validate_positive_decimal(self.price_cny)
        _validate_paintwear(self.paintwear)
        _validate_exact_string(self.asset_id, field="asset_id")
        _validate_exact_string(self.source, field="source")


def _validate_exact_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TradeUpInputCandidateValidationError(field=field)
    return value


def _validate_positive_decimal(value: object) -> None:
    if (
        type(value) is not Decimal
        or not value.is_finite()
        or value <= 0
    ):
        raise TradeUpInputCandidateValidationError(field="price_cny")


def _validate_paintwear(value: object) -> None:
    if (
        type(value) is not Decimal
        or not value.is_finite()
        or not Decimal("0") <= value <= Decimal("1")
    ):
        raise TradeUpInputCandidateValidationError(field="paintwear")
