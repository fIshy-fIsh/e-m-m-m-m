"""Real pinned-snapshot integration test for the identity-binding layer.

This test exercises the actual pinned community catalog snapshot and
proves the missing production seam:

  BuffListingProvider
    → IdentityResolvingBuffListingProvider
    → BuffListingCandidateAdapter

...with the local offline resolver only. No network. No fallback I/O.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_identity_listing_provider import (
    IdentityResolvingBuffListingProvider,
)
from app.services.buff_intrinsic_flag_listing_provider import (
    bind_intrinsic_flags_to_provider,
)
from app.services.buff_intrinsic_flag_resolver import (
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_listing_candidate_adapter import convert_buff_listings
from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    enrich_candidates,
)


async def _wrap_with_intrinsic_flags(
    identity_bound: IdentityResolvingBuffListingProvider,
    goods_id: str,
) -> list[BuffListing]:
    """Run identity binding then attach canonical-name intrinsic flags."""
    intrinsic = CanonicalNameIntrinsicFlagResolver()
    full_bound = bind_intrinsic_flags_to_provider(identity_bound, intrinsic)
    return await full_bound.get_listings(goods_id)

SNAPSHOT_PATH = Path("data/identity/buff_identity_v1.json")


@dataclass(frozen=True)
class _StubProvider:
    """A single-goods_id stub provider that returns one synthetic listing."""

    listings: tuple[BuffListing, ...]
    requested_goods_id: str

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        assert goods_id == self.requested_goods_id
        return list(self.listings)


def _make_listing(*, goods_id: str, listing_id: str, asset_id: str) -> BuffListing:
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=None,
        price_cny=Decimal("100.00"),
        paintwear=Decimal("0.123456"),
        asset_id=asset_id,
        paintseed=1,
        source="buff",
    )


@pytest.fixture(scope="module")
def resolver() -> BuffCommunityIdentityResolver:
    if not SNAPSHOT_PATH.exists():
        pytest.skip(f"pinned snapshot not present at {SNAPSHOT_PATH}")
    return BuffCommunityIdentityResolver.from_snapshot_path(SNAPSHOT_PATH)


def test_pinned_snapshot_resolves_real_listing_to_real_market_hash_name(
    resolver: BuffCommunityIdentityResolver,
) -> None:
    """Choose a real goods_id from the pinned snapshot; verify exact binding."""
    real_goods_id = "33960"  # AK-47 | Redline (Field-Tested) in the pinned snapshot
    expected_name = "AK-47 | Redline (Field-Tested)"

    provider = _StubProvider(
        listings=(
            _make_listing(
                goods_id=real_goods_id,
                listing_id="listing-pinned-1",
                asset_id="asset-pinned-1",
            ),
        ),
        requested_goods_id=real_goods_id,
    )
    bound = IdentityResolvingBuffListingProvider(provider=provider, resolver=resolver)

    listings = asyncio.run(bound.get_listings(real_goods_id))
    assert len(listings) == 1
    assert listings[0].market_hash_name == expected_name
    assert listings[0].goods_id == real_goods_id


def test_pinned_snapshot_full_seam_to_enriched_input(
    resolver: BuffCommunityIdentityResolver,
) -> None:
    """End-to-end seam: provider → binding → adapter → enricher → InputItem."""
    real_goods_id = "42998"  # ★ Karambit | Doppler (Factory New)
    expected_name = "★ Karambit | Doppler (Factory New)"

    provider = _StubProvider(
        listings=(
            _make_listing(
                goods_id=real_goods_id,
                listing_id="listing-pinned-2",
                asset_id="asset-pinned-2",
            ),
        ),
        requested_goods_id=real_goods_id,
    )
    bound = IdentityResolvingBuffListingProvider(provider=provider, resolver=resolver)

    listings = asyncio.run(
        _wrap_with_intrinsic_flags(bound, real_goods_id)
    )

    candidates = convert_buff_listings(listings)
    assert len(candidates) == 1
    assert candidates[0].market_hash_name == expected_name
    # ★ Karambit | Doppler starts with neither canonical prefix
    assert candidates[0].stattrak is False
    assert candidates[0].souvenir is False

    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver(
            {
                expected_name: TradeUpInputMetadata(
                    market_hash_name=expected_name,
                    collection_name="C",
                    rarity="R",
                    min_float=0.0,
                    max_float=1.0,
                ),
            }
        )
    )
    result = enrich_candidates(candidates, enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0
    item = result.enriched[0].input_item
    assert item.market_hash_name == expected_name
    assert item.price_cny == Decimal("100.00")


def test_pinned_snapshot_unknown_goods_id_yields_none_name(
    resolver: BuffCommunityIdentityResolver,
) -> None:
    """A well-formed but unknown goods_id leaves market_hash_name=None."""
    unknown_id = "99999999"

    provider = _StubProvider(
        listings=(
            _make_listing(
                goods_id=unknown_id,
                listing_id="listing-unknown",
                asset_id="asset-unknown",
            ),
        ),
        requested_goods_id=unknown_id,
    )
    bound = IdentityResolvingBuffListingProvider(provider=provider, resolver=resolver)

    listings = asyncio.run(bound.get_listings(unknown_id))
    assert len(listings) == 1
    assert listings[0].market_hash_name is None