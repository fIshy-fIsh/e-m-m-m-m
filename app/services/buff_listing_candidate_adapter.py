from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_candidate import TradeUpInputCandidate

__all__ = (
    "CandidateAdapterRejectionReason",
    "CandidateAdapterRejection",
    "BuffListingCandidateAdapter",
    "convert_buff_listing_to_candidate",
    "convert_buff_listings",
)


_ALLOWED_SOURCES: frozenset[str] = frozenset({"buff"})


class CandidateAdapterRejectionReason(StrEnum):
    """Closed vocabulary for candidate-adapter rejections.

    The adapter does not own identity derivation. Unresolved identity flows
    through as a candidate with `market_hash_name=None`; downstream
    `TradeUpInputEnrichment` rejects it as `MARKET_HASH_NAME_UNRESOLVED`.
    """

    MISSING_IDENTITY = "missing_identity"
    MISSING_PRICE = "missing_price"
    INVALID_FLOAT = "invalid_float"
    MISSING_ASSET_ID = "missing_asset_id"
    UNSUPPORTED_SOURCE = "unsupported_source"


@dataclass(frozen=True, kw_only=True, repr=False)
class CandidateAdapterRejection:
    """One rejected listing at the adapter boundary.

    Holds the listing reference (for diagnostics) and the rejection reason.
    `__repr__` and `__str__` expose only the rejection code and the source
    tag; never any value field of the rejected listing.

    The listing field is duck-typed: any object with the BuffListing
    attribute surface is accepted. The adapter does not need to import the
    `BuffListing` type into a runtime check; its job is to carry a reason.
    """

    listing: object
    reason: CandidateAdapterRejectionReason

    def __post_init__(self) -> None:
        if type(self.reason) is not CandidateAdapterRejectionReason:
            raise ValueError("reason must be a CandidateAdapterRejectionReason")

    def __repr__(self) -> str:
        return f"CandidateAdapterRejection(reason={self.reason.name})"

    def __str__(self) -> str:
        return f"CandidateAdapterRejection(reason={self.reason.name})"


class BuffListingCandidateAdapter(Protocol):
    """Convert one BuffListing into one candidate or one rejection."""

    def convert(
        self,
        listing: BuffListing,
    ) -> TradeUpInputCandidate | CandidateAdapterRejection:
        """Return one candidate or one rejection; never raise for documented reasons."""


def convert_buff_listing_to_candidate(
    listing: BuffListing,
) -> TradeUpInputCandidate | CandidateAdapterRejection:
    """Convert one BuffListing into one TradeUpInputCandidate or one rejection.

    The adapter does not own identity derivation. When
    `BuffListing.market_hash_name` is `None`, the adapter returns a candidate
    with `market_hash_name=None`; the downstream `TradeUpInputEnrichment`
    will surface that as `MARKET_HASH_NAME_UNRESOLVED`. `MISSING_IDENTITY`
    is reserved for explicit refusal at the adapter layer and is not
    triggered in this synthetic phase.
    """

    if not hasattr(listing, "market_hash_name"):
        raise TypeError("listing must expose market_hash_name")

    price = getattr(listing, "price_cny", None)
    if (
        type(price) is not Decimal
        or not price.is_finite()
        or price <= 0
    ):
        return CandidateAdapterRejection(
            listing=listing,
            reason=CandidateAdapterRejectionReason.MISSING_PRICE,
        )

    paintwear = getattr(listing, "paintwear", None)
    if (
        type(paintwear) is not Decimal
        or not paintwear.is_finite()
        or not Decimal("0") <= paintwear <= Decimal("1")
    ):
        return CandidateAdapterRejection(
            listing=listing,
            reason=CandidateAdapterRejectionReason.INVALID_FLOAT,
        )

    asset_id = getattr(listing, "asset_id", None)
    if (
        type(asset_id) is not str
        or not asset_id
        or asset_id != asset_id.strip()
    ):
        return CandidateAdapterRejection(
            listing=listing,
            reason=CandidateAdapterRejectionReason.MISSING_ASSET_ID,
        )

    source = getattr(listing, "source", None)
    if source not in _ALLOWED_SOURCES:
        return CandidateAdapterRejection(
            listing=listing,
            reason=CandidateAdapterRejectionReason.UNSUPPORTED_SOURCE,
        )

    market_hash_name: str | None = getattr(listing, "market_hash_name", None)
    goods_id: str = getattr(listing, "goods_id", "")
    listing_id: str = getattr(listing, "listing_id", "")

    return TradeUpInputCandidate(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=price,
        paintwear=paintwear,
        asset_id=asset_id,
        source=source,
        stattrak=False,
        souvenir=False,
    )


def convert_buff_listings(
    listings: Sequence[BuffListing],
) -> tuple[TradeUpInputCandidate, ...]:
    """Convert a sequence of listings; return kept candidates in input order.

    Rejected listings are dropped. The caller is responsible for keeping
    rejection histograms; the adapter does not return them here.
    """

    kept: list[TradeUpInputCandidate] = []
    for listing in listings:
        outcome = convert_buff_listing_to_candidate(listing)
        if isinstance(outcome, TradeUpInputCandidate):
            kept.append(outcome)
    return tuple(kept)