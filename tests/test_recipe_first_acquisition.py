"""Phase 16E — Existing BUFF acquisition/enrichment composition tests."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    BuffListingIntrinsicFlagsValue,
)
from app.services.buff_listing_provider import BuffListing
from app.services.recipe_first_acquisition import (
    ExistingRecipeFirstAcquisitionPipeline,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver

ROOT = Path(__file__).resolve().parent.parent


def _listing(
    *,
    listing_id: str,
    goods_id: str,
    market_hash_name: str | None,
    price: str = "1",
    paintwear: str = "0.10",
    asset: str | None = None,
) -> BuffListing:
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal(price),
        paintwear=Decimal(paintwear),
        asset_id=asset or listing_id,
        paintseed=None,
        source="buff",
    )


@dataclass
class FakeRawProvider:
    pages: dict[str, list[BuffListing]]

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        return list(self.pages.get(goods_id, ()))


class FixedResolver(BuffListingIntrinsicFlagResolver):
    def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
        return BuffListingIntrinsicFlagsValue(
            stattrak=market_hash_name.startswith("StatTrak™ "),
            souvenir=market_hash_name.startswith("Souvenir "),
        )


async def _run(pipeline, *, goods_id, market_hash_name):
    return await pipeline.acquire_page(
        goods_id=goods_id, market_hash_name=market_hash_name
    )


def test_acquisition_pipeline_propagates_through_all_stages() -> None:
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        ROOT / "data" / "metadata" / "skin_metadata_v1.json"
    )
    target_name = "'Blueberries' Buckshot | NSWC SEAL"
    goods_id = "835687"
    listings = [
        _listing(
            listing_id=f"L{i}",
            goods_id=goods_id,
            market_hash_name=target_name,
            asset=f"asset-{i}",
        )
        for i in range(5)
    ]
    pipeline = ExistingRecipeFirstAcquisitionPipeline(
        listing_provider=FakeRawProvider({goods_id: listings}),
        identity_resolver=identity,
        metadata_resolver=metadata,
        intrinsic_resolver=FixedResolver(),
    )

    result = asyncio_run(pipeline, goods_id=goods_id, market_hash_name=target_name)
    counts = result.counts
    assert counts.listings_received == len(listings)
    assert counts.identity_resolved == len(listings)
    assert counts.intrinsic_resolved == len(listings)
    assert counts.candidate_accepted == len(listings)
    assert counts.identity_unresolved == 0
    assert counts.intrinsic_unresolved == 0
    assert counts.candidate_rejected == 0


def test_acquisition_pipeline_preserves_redaction() -> None:
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        ROOT / "data" / "metadata" / "skin_metadata_v1.json"
    )
    target_name = "'Blueberries' Buckshot | NSWC SEAL"
    goods_id = "835687"
    listings = [
        _listing(listing_id="L1", goods_id=goods_id, market_hash_name=target_name),
        _listing(
            listing_id="L1",
            goods_id=goods_id,
            market_hash_name=target_name,
            paintwear="0.20",
        ),
    ]
    pipeline = ExistingRecipeFirstAcquisitionPipeline(
        listing_provider=FakeRawProvider({goods_id: listings}),
        identity_resolver=identity,
        metadata_resolver=metadata,
        intrinsic_resolver=FixedResolver(),
    )
    with pytest.raises(ValueError, match="duplicate listing_id"):
        asyncio_run(
            pipeline, goods_id=goods_id, market_hash_name=target_name
        )


def test_acquisition_pipeline_duplicates_assets_still_rejected() -> None:
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        ROOT / "data" / "metadata" / "skin_metadata_v1.json"
    )
    target_name = "'Blueberries' Buckshot | NSWC SEAL"
    goods_id = "835687"
    listings = [
        _listing(listing_id="L1", goods_id=goods_id, market_hash_name=target_name),
        _listing(
            listing_id="L2",
            goods_id=goods_id,
            market_hash_name=target_name,
            asset="asset-other",
        ),
    ]
    pipeline = ExistingRecipeFirstAcquisitionPipeline(
        listing_provider=FakeRawProvider({goods_id: listings}),
        identity_resolver=identity,
        metadata_resolver=metadata,
        intrinsic_resolver=FixedResolver(),
    )
    result = asyncio_run(
        pipeline, goods_id=goods_id, market_hash_name=target_name
    )
    counts = result.counts
    assert counts.listings_received == 2
    assert counts.candidate_accepted == 2


def asyncio_run(pipeline, *, goods_id: str, market_hash_name: str):
    import asyncio

    return asyncio.run(
        pipeline.acquire_page(goods_id=goods_id, market_hash_name=market_hash_name)
    )