"""Phase17D-R1 offline reproduction of the prescreen provider-failure boundary.

Pure/offline only. All external market seams are fakes; no HTTP.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.price_cache import InMemoryPriceCache
from app.services.recipe_family import build_recipe_family
from app.services.recipe_first_runtime_contract import (
    RecipeFirstDiscoveryBudget,
    RecipeFirstOutputFormat,
    RecipeFirstRuntimeConfig,
    RecipeFirstRuntimeTerminalCode,
    RecipeFirstRuntimeTerminalGroup,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.static_float_feasibility import compute_static_float_feasibility
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.valuation_service import ValuationConfig, ValuationService

ROOT = Path(__file__).resolve().parent.parent
IDENTITY_PATH = ROOT / "data" / "identity" / "buff_identity_v1.json"
METADATA_PATH = ROOT / "data" / "metadata" / "skin_metadata_v1.json"


class _FakeBatchTransport:
    """In-memory fake that yields 10 strict-BUFF quotes on the first batch
    and raises on the second to mirror Phase17D's transport-error boundary.
    """

    def __init__(self, *, fail_on_call: int = 2) -> None:
        self.fail_on_call = fail_on_call
        self.call_count = 0

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: Any = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> Any:
        self.call_count += 1
        if self.call_count == self.fail_on_call:
            raise RuntimeError("provider transport failure")

        # In-memory strict-BUFF quote shape, matches SteamDTBatchPriceResult.
        from app.clients.steamdt_client import SteamDTBatchPriceResult

        rows = [
            {
                "marketHashName": name,
                "dataList": [
                    {
                        "platform": "BUFF",
                        "platformItemId": "1",
                        "sellPrice": "100.0",
                        "sellCount": 100,
                        "biddingPrice": "0",
                        "biddingCount": 0,
                        "updateTime": 1780000000,
                    }
                ],
            }
            for name in market_hash_names
        ]
        return SteamDTBatchPriceResult(
            quotes={}, missing=[], raw={"success": True, "data": rows}
        )


class _FakeBuffProvider:
    async def get_listings(self, goods_id: str) -> list:
        raise AssertionError("BUFF must not run on a prescreen provider failure")


class _FakePriceProvider:
    async def get_price(self, market_hash_name: str):
        raise AssertionError("final price must not run on a prescreen failure")

    async def get_prices(self, names):
        raise AssertionError("final prices must not run on a prescreen failure")


def _build_coordinator() -> RecipeFirstRuntimeCoordinator:
    identity = BuffCommunityIdentityResolver.from_snapshot_path(IDENTITY_PATH)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    finish = StructuralOutputFinishIndex.from_skins(metadata.skins)
    family = build_recipe_family(
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
    )
    # Force in-scope state so discovery visits exactly the frozen Phoenix family.
    feasibility = compute_static_float_feasibility(
        family,
        skins=metadata.skins,
        identity_resolver=identity,
        finish_index=finish,
    )
    assert feasibility.family_hash == family.family_hash
    batch_transport = _FakeBatchTransport(fail_on_call=2)
    return RecipeFirstRuntimeCoordinator(
        config=RecipeFirstRuntimeConfig(
            enabled=True,
            preview=False,
            input_rarities=("Classified",),
            stattrak_modes=(StatTrakMode.NORMAL,),
            collection_allowlist=("The Phoenix Collection",),
            max_targeted_buff_goods_ids=10,
            max_final_valuation_requests=2,
            sell_fee_rate=Decimal("0.025"),
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=1,
                max_candidate_states_explored=256,
            ),
            cache_backend="inmemory",
            output_format=RecipeFirstOutputFormat.JSON,
        ),
        discovery_budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=1,
            max_prescreen_names=20,
            max_prescreen_batch_dispatches=2,
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish,
        prescreen_transport=batch_transport,
        listing_provider=_FakeBuffProvider(),
        valuation_service=ValuationService(
            _FakePriceProvider(),
            ValuationConfig(require_all_prices=True),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("0"),
            min_expected_profit_cny=Decimal("0"),
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("1"),
        ),
        cached_price_resolver=ScannerCachedBuffPriceResolver(InMemoryPriceCache()),
        family_iterator_factory=lambda _generator: iter((family,)),
    )


def test_phase17d_failure_boundary_is_reproducible_offline() -> None:
    coordinator = _build_coordinator()
    report = asyncio.run(coordinator.run_once())

    assert report.terminal_group is (
        RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER
    )
    assert report.terminal_code is (
        RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    )
    assert "PRESCREEN_PROVIDER_FAILURE" in report.safe_error_codes
    assert "EXTERNAL_PROVIDER_FAILURE" in report.incompleteness_flags

    counters = report.counters
    assert counters.families_visited == 1
    assert counters.prescreen_logical_requested == 19
    assert counters.prescreen_unique_after_dedupe == 19
    assert counters.prescreen_attempted == 19
    assert counters.prescreen_dispatch_started == 2
    assert counters.prescreen_succeeded == 10
    assert counters.prescreen_missing == 9
    assert counters.prescreen_transport_error_count == 1
    assert counters.buff_dispatch_started == 0
    assert counters.live_attempted == 0
    assert counters.evaluations_total == 0
    assert counters.opportunities_found == 0
    assert counters.fallback_family_used is False

    assert report.evidence.concrete_output_names == ()
    assert report.evidence.final_quote_market_hash_names == ()
    assert report.evidence.evaluations == ()

    # Two phase observations: discovery ok and prescreen failed.
    names = [phase.name for phase in report.phases]
    assert names == ["discovery", "prescreen"]
    assert report.phases[0].status == "ok"
    assert report.phases[1].status == "failed"
    assert "transport_errors=1" in report.phases[1].detail
