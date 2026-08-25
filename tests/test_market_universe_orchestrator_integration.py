"""Phase 13R — Auto-universe → real scanner integration test.

Pinned Cobblestone Collection pair:

- goods_id 34279 → CZ75-Auto | Chalice (Factory New)  (normal, Restricted)
- goods_id 37551 → Souvenir CZ75-Auto | Chalice (Factory New)

The auto-universe builder must produce exactly these two goods_ids
under `--rarity Restricted --stattrak-mode normal --souvenir include`.
The real `LiveScannerOrchestrator.run_once` consumes them with the
existing pinned identity + metadata catalogs and runs the real
composition seam. No network, no HTTP clients, no actual BUFF calls.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import BuffCommunityIdentityResolver
from app.services.market_universe_builder import (
    MarketUniverseSpec,
    SouvenirInclusion,
    StatTrakMode,
    build_universe_goods_ids,
)
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_orchestrator import LiveScannerOrchestrator
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver

CHALICE_NORMAL = "CZ75-Auto | Chalice (Factory New)"
CHALICE_SOUVENIR = "Souvenir CZ75-Auto | Chalice (Factory New)"
NORMAL_GOODS_ID = "34279"
SOUVENIR_GOODS_ID = "37551"


@dataclass(frozen=True)
class _IdentityMetadataPair:
    identity: BuffCommunityIdentityResolver
    metadata: PinnedSkinMetadataResolver


def _load_pinned_pair(
    *,
    identity_path: Path,
    metadata_path: Path,
) -> _IdentityMetadataPair:
    return _IdentityMetadataPair(
        identity=BuffCommunityIdentityResolver.from_snapshot_path(identity_path),
        metadata=PinnedSkinMetadataResolver.from_snapshot_path(metadata_path),
    )


def _listings_payload(
    *,
    goods_id: str,
    asset_prefix: str,
    listing_prefix: str,
    price: str,
    paintwear_range: Sequence[tuple[str, str]],
) -> bytes:
    items = []
    for index, (lo, _hi) in enumerate(paintwear_range):
        items.append(
            {
                "id": f"{listing_prefix}-{index}",
                "price": price,
                "asset_info": {
                    "paintwear": lo,
                    "assetid": f"{asset_prefix}-{index}",
                    "paintseed": 100 + index,
                },
            }
        )
    payload = {
        "code": "OK",
        "data": {"items": items, "goods_id": goods_id},
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class _FakePayloadClient:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self._payloads = payloads
        self.calls: list[str] = []

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        self.calls.append(goods_id)
        return self._payloads[goods_id]


@pytest.fixture
def pinned_pair(tmp_path: Path) -> _IdentityMetadataPair:
    identity_path = Path("data/identity/buff_identity_v1.json")
    metadata_path = Path("data/metadata/skin_metadata_v1.json")
    if not identity_path.exists() or not metadata_path.exists():
        pytest.skip("pinned identity/metadata snapshots not present")
    return _load_pinned_pair(
        identity_path=identity_path, metadata_path=metadata_path
    )


def test_pinned_chalice_pair_produces_two_canonical_normal_outputs(
    pinned_pair: _IdentityMetadataPair,
) -> None:
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=2,
        collection_allowlist=("The Cobblestone Collection",),
    )
    universe = build_universe_goods_ids(
        identity_resolver=pinned_pair.identity,
        metadata_resolver=pinned_pair.metadata,
        spec=spec,
    )
    assert len(universe.goods_ids) == 2
    assert NORMAL_GOODS_ID in universe.goods_ids
    assert universe.diagnostics.selected_count == 2
    assert universe.diagnostics.excluded_by_allowlist >= 1
    assert all(
        "Chalice" in name for name in universe.selected_market_hash_names
    )

    payloads: dict[str, bytes] = {}
    for index, goods_id in enumerate(universe.goods_ids):
        payloads[goods_id] = _listings_payload(
            goods_id=goods_id,
            asset_prefix=f"asset-{index}",
            listing_prefix=f"listing-{index}",
            price="12.50",
            paintwear_range=[
                ("0.01", "0.05"),
                ("0.02", "0.06"),
                ("0.03", "0.07"),
                ("0.04", "0.08"),
                ("0.05", "0.09"),
            ],
        )
    payload_client = _FakePayloadClient(payloads)
    from app.services.buff_listing_provider import BuffListingProvider

    provider = BuffListingProvider(payload_client)

    orchestrator = LiveScannerOrchestrator(
        listing_provider=provider,
        identity_resolver=pinned_pair.identity,
        metadata_resolver=pinned_pair.metadata,
        max_valuation_requests_per_run=20,
        valuation_service=None,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("-1"),
            min_expected_profit_cny=Decimal("0"),
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("999999"),
        ),
    )

    result = asyncio.run(orchestrator.run_once(list(universe.goods_ids)))
    assert result.counters.goods_ids_succeeded == len(universe.goods_ids)
    assert result.counters.listings_received == 10
    assert result.counters.input_items_created == 10
    assert result.counters.recipes_evaluated >= 1
    assert payload_client.calls == list(universe.goods_ids)
    evaluation = result.recipe_evaluations[0]
    assert evaluation.output_market_hash_names_requested == (
        "M4A1-S | Knight (Factory New)",
        "M4A1-S | Knight (Minimal Wear)",
    )
    assert evaluation.metrics is None
    assert evaluation.valuation_prices_resolved == 0


def test_auto_universe_drives_full_seam_including_souvenir_inputs(
    pinned_pair: _IdentityMetadataPair,
) -> None:
    """A universe with one normal and one Souvenir goods_id proves both reach the recipe."""
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=2,
        collection_allowlist=("The Cobblestone Collection",),
    )
    universe = build_universe_goods_ids(
        identity_resolver=pinned_pair.identity,
        metadata_resolver=pinned_pair.metadata,
        spec=spec,
    )
    assert all(
        "Chalice" in name for name in universe.selected_market_hash_names
    )

    payloads: dict[str, bytes] = {}
    for index, goods_id in enumerate(universe.goods_ids):
        payloads[goods_id] = _listings_payload(
            goods_id=goods_id,
            asset_prefix=f"asset-{index}",
            listing_prefix=f"listing-{index}",
            price="12.50",
            paintwear_range=[
                ("0.01", "0.05"),
                ("0.02", "0.06"),
                ("0.03", "0.07"),
                ("0.04", "0.08"),
                ("0.05", "0.09"),
            ],
        )
    payload_client = _FakePayloadClient(payloads)
    from app.services.buff_listing_provider import BuffListingProvider

    provider = BuffListingProvider(payload_client)

    orchestrator = LiveScannerOrchestrator(
        listing_provider=provider,
        identity_resolver=pinned_pair.identity,
        metadata_resolver=pinned_pair.metadata,
        max_valuation_requests_per_run=20,
        valuation_service=None,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("-1"),
            min_expected_profit_cny=Decimal("0"),
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("999999"),
        ),
    )

    result = asyncio.run(orchestrator.run_once(list(universe.goods_ids)))
    assert result.counters.recipes_evaluated >= 1
    evaluation = result.recipe_evaluations[0]
    assert evaluation.output_market_hash_names_requested == (
        "M4A1-S | Knight (Factory New)",
        "M4A1-S | Knight (Minimal Wear)",
    )
    assert evaluation.valuation_prices_resolved == 0