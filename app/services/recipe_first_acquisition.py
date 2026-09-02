"""Phase 16E — Existing BUFF acquisition/enrichment composition.

This adapter composes the existing raw listing provider, exact pinned identity
binding, canonical intrinsic classification, candidate adapter, and metadata
enrichment. It returns only immutable normalized evidence and redacted stage
counts; no raw BUFF payload or seller/account data is retained.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.services.buff_community_identity_resolver import (
    BuffGoodsIdIdentityResolver,
)
from app.services.buff_identity_listing_provider import bind_identity_to_provider
from app.services.buff_intrinsic_flag_listing_provider import (
    bind_intrinsic_flags_to_provider,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_listing_candidate_adapter import (
    CandidateAdapterRejection,
    convert_buff_listing_to_candidate,
)
from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    TradeUpInputMetadataResolver,
    enrich_candidates,
)

__all__ = (
    "ExistingRecipeFirstAcquisitionPipeline",
    "RecipeFirstAcquisitionPage",
    "RecipeFirstAcquisitionPageProvider",
    "RecipeFirstAcquisitionStageCounts",
    "RecipeFirstListingProvenance",
)


class RawBuffListingPageProvider(Protocol):
    async def get_listings(self, goods_id: str) -> list[BuffListing]: ...


class RecipeFirstAcquisitionPageProvider(Protocol):
    async def acquire_page(
        self,
        *,
        goods_id: str,
        market_hash_name: str,
    ) -> RecipeFirstAcquisitionPage: ...


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstListingProvenance:
    """Safe normalized listing provenance retained through evaluation."""

    listing_id: str
    goods_id: str
    asset_id: str
    market_hash_name: str
    price_cny: Decimal
    paintwear: Decimal
    paintseed: int | None
    stattrak: bool
    souvenir: bool
    source: str


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstAcquisitionStageCounts:
    listings_received: int
    identity_resolved: int
    identity_unresolved: int
    intrinsic_resolved: int
    intrinsic_unresolved: int
    candidate_accepted: int
    candidate_rejected: int
    metadata_resolved: int
    metadata_unresolved: int


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstAcquisitionPage:
    goods_id: str
    market_hash_name: str
    enriched_inputs: tuple[TradeUpEnrichedInput, ...]
    provenance: tuple[RecipeFirstListingProvenance, ...]
    counts: RecipeFirstAcquisitionStageCounts
    candidate_rejection_histogram: tuple[tuple[str, int], ...]
    metadata_rejection_histogram: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if len(self.enriched_inputs) != len(self.provenance):
            raise ValueError(
                "acquisition enriched inputs and provenance must align"
            )
        enriched_ids = tuple(
            entry.candidate.listing_id for entry in self.enriched_inputs
        )
        provenance_ids = tuple(entry.listing_id for entry in self.provenance)
        if enriched_ids != provenance_ids:
            raise ValueError("acquisition provenance order must align")


@dataclass(kw_only=True, repr=False)
class ExistingRecipeFirstAcquisitionPipeline:
    """Concrete composition of the existing acquisition/enrichment stages."""

    listing_provider: RawBuffListingPageProvider
    identity_resolver: BuffGoodsIdIdentityResolver
    metadata_resolver: TradeUpInputMetadataResolver
    intrinsic_resolver: BuffListingIntrinsicFlagResolver | None = None

    def __post_init__(self) -> None:
        identity_provider = bind_identity_to_provider(
            self.listing_provider,
            self.identity_resolver,
        )
        self._intrinsic_provider = bind_intrinsic_flags_to_provider(
            identity_provider,
            self.intrinsic_resolver or CanonicalNameIntrinsicFlagResolver(),
        )
        self._enricher = InMemoryTradeUpInputEnricher(self.metadata_resolver)

    async def acquire_page(
        self,
        *,
        goods_id: str,
        market_hash_name: str,
    ) -> RecipeFirstAcquisitionPage:
        listings = await self._intrinsic_provider.get_listings(goods_id)
        typed: tuple[BuffListingIntrinsicFlags, ...] = tuple(  # type: ignore[assignment]
            listings  # type: ignore[arg-type]
        )
        identity_resolved = sum(
            listing.market_hash_name is not None for listing in typed
        )
        intrinsic_resolved = sum(
            listing.stattrak is not None and listing.souvenir is not None
            for listing in typed
        )
        candidates: list[TradeUpInputCandidate] = []
        candidate_rejections: Counter[str] = Counter()
        listing_by_id: dict[str, BuffListingIntrinsicFlags] = {}
        for listing in typed:
            if (
                listing.goods_id != goods_id
                or listing.market_hash_name != market_hash_name
            ):
                raise ValueError(
                    "acquired listing does not match exact requested identity"
                )
            if listing.listing_id in listing_by_id:
                raise ValueError("duplicate listing_id within acquired page")
            assert isinstance(listing, BuffListingIntrinsicFlags)
            listing_by_id[listing.listing_id] = listing
            converted = convert_buff_listing_to_candidate(listing)  # type: ignore[arg-type]
            if isinstance(converted, CandidateAdapterRejection):
                candidate_rejections[converted.reason.value] += 1
            else:
                candidates.append(converted)
        enrichment = enrich_candidates(candidates, self._enricher)
        metadata_rejections: Counter[str] = Counter(
            rejection.reason.value for rejection in enrichment.rejected
        )
        provenance: list[RecipeFirstListingProvenance] = []
        for enriched in enrichment.enriched:
            listing = listing_by_id[enriched.candidate.listing_id]
            provenance.append(
                RecipeFirstListingProvenance(
                    listing_id=listing.listing_id,
                    goods_id=listing.goods_id,
                    asset_id=listing.asset_id,
                    market_hash_name=listing.market_hash_name or "",
                    price_cny=listing.price_cny,
                    paintwear=listing.paintwear,
                    paintseed=listing.paintseed,
                    stattrak=listing.stattrak or False,
                    souvenir=listing.souvenir or False,
                    source=listing.source,
                )
            )
        return RecipeFirstAcquisitionPage(
            goods_id=goods_id,
            market_hash_name=market_hash_name,
            enriched_inputs=enrichment.enriched,
            provenance=tuple(provenance),
            counts=RecipeFirstAcquisitionStageCounts(
                listings_received=len(typed),
                identity_resolved=identity_resolved,
                identity_unresolved=len(typed) - identity_resolved,
                intrinsic_resolved=intrinsic_resolved,
                intrinsic_unresolved=len(typed) - intrinsic_resolved,
                candidate_accepted=len(candidates),
                candidate_rejected=len(typed) - len(candidates),
                metadata_resolved=len(enrichment.enriched),
                metadata_unresolved=len(enrichment.rejected),
            ),
            candidate_rejection_histogram=tuple(
                sorted(candidate_rejections.items())
            ),
            metadata_rejection_histogram=tuple(
                sorted(metadata_rejections.items())
            ),
        )
