from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagsValue,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.buff_listing_provider import BuffListing
from app.services.price_cache import (
    CachedPriceSnapshot,
    InMemoryPriceCache,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
)
from app.services.price_provider import MockPriceProvider, PriceLookupResult, PriceQuote
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeEnumerationConfig,
    RecipeSolverConfig,
)
from app.services.risk_filter import (
    SOUVENIR_EXCLUDED,
    RiskDecision,
    RiskFilterConfig,
)
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_orchestrator import LiveScannerOrchestrator
from app.services.scanner_recipe_composition import (
    ScannerRecipeBucketDiagnostics,
    ScannerRecipeCompositionDiagnostics,
    ScannerRecipeCompositionResult,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.steamdt_cached_price_resolver import SteamDTCachedPriceResolver
from app.services.tradeup_engine import InputItem, TradeupResult
from app.services.valuation_service import ValuationConfig, ValuationService

INPUT_NAME = "AK-47 | Redline (Field-Tested)"
OUTPUT_NAME = "M4A4 | Asiimov (Factory New)"
GOODS_ID = "33960"


def _listing(index: int, *, name: str | None = None) -> BuffListing:
    return BuffListing(
        listing_id=f"listing-{index}",
        goods_id=GOODS_ID,
        market_hash_name=name,
        price_cny=Decimal("10.00") + Decimal(index) / Decimal("100"),
        paintwear=Decimal("0.15") + Decimal(index) / Decimal("10000"),
        asset_id=f"asset-{index}",
        paintseed=index,
        source="buff",
    )


class FakeListingProvider:
    def __init__(
        self,
        *,
        listings_by_goods: dict[str, list[BuffListing]] | None = None,
        fail_goods: set[str] | None = None,
        memory_error: bool = False,
    ) -> None:
        self.listings_by_goods = listings_by_goods or {
            GOODS_ID: [_listing(i) for i in range(10)]
        }
        self.fail_goods = fail_goods or set()
        self.memory_error = memory_error
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        if self.memory_error:
            raise MemoryError("sentinel")
        if goods_id in self.fail_goods:
            raise RuntimeError("fake fetch failure")
        return list(self.listings_by_goods.get(goods_id, []))


class FakeIdentityResolver:
    def __init__(
        self,
        *,
        unresolved: bool = False,
        names_by_goods: dict[str, str] | None = None,
    ) -> None:
        self.unresolved = unresolved
        self.names_by_goods = names_by_goods or {}
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
        self.calls.append(goods_id)
        if self.unresolved:
            return None
        return BuffItemIdentity(
            market_hash_name=self.names_by_goods.get(goods_id, INPUT_NAME),
            goods_id=goods_id,
        )


def _metadata_resolver() -> PinnedSkinMetadataResolver:
    return PinnedSkinMetadataResolver.from_payload(
        {
            "items": [
                {
                    "market_hash_name": INPUT_NAME,
                    "collection_name": "Test Collection",
                    "rarity": "Restricted",
                    "min_float": 0.10,
                    "max_float": 0.70,
                    "name": "AK-47 | Redline",
                    "weapon": "AK-47",
                    "category": "Rifle",
                    "stattrak": False,
                    "souvenir": False,
                    "paint_index": 282,
                },
                {
                    "market_hash_name": OUTPUT_NAME,
                    "collection_name": "Test Collection",
                    "rarity": "Classified",
                    "min_float": 0.00,
                    "max_float": 0.08,
                    "name": "M4A4 | Asiimov",
                    "weapon": "M4A4",
                    "category": "Rifle",
                    "stattrak": False,
                    "souvenir": False,
                    "paint_index": 255,
                },
            ]
        }
    )


def _orchestrator(
    *,
    provider: FakeListingProvider | None = None,
    identity: FakeIdentityResolver | None = None,
    metadata: PinnedSkinMetadataResolver | None = None,
    with_valuation: bool = True,
    min_expected_profit: Decimal = Decimal("0"),
    max_valuation_requests: int = 10,
    price_provider: MockPriceProvider | None = None,
    exclude_souvenir: bool = False,
    intrinsic_resolver: object | None = None,
    enumeration_config: RecipeEnumerationConfig | None = None,
    cached_price_resolver: ScannerCachedBuffPriceResolver | None = None,
) -> LiveScannerOrchestrator:
    valuation: ValuationService | None = None
    if with_valuation:
        provider_to_use = price_provider or MockPriceProvider(
            {
                OUTPUT_NAME: PriceQuote(
                    market_hash_name=OUTPUT_NAME,
                    price_cny=Decimal("200.00"),
                    source="test",
                )
            }
        )
        valuation = ValuationService(
            provider_to_use,
            ValuationConfig(),
        )
    return LiveScannerOrchestrator(
        listing_provider=provider or FakeListingProvider(),  # type: ignore[arg-type]
        identity_resolver=identity or FakeIdentityResolver(),
        metadata_resolver=metadata or _metadata_resolver(),
        intrinsic_resolver=intrinsic_resolver,  # type: ignore[arg-type]
        valuation_service=valuation,
        cached_price_resolver=cached_price_resolver,
        max_valuation_requests_per_run=max_valuation_requests,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0"),
        ),
        enumeration_config=enumeration_config,
        risk_config=RiskFilterConfig(
            min_roi=Decimal("-1"),
            min_expected_profit_cny=min_expected_profit,
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("999999"),
            exclude_souvenir=exclude_souvenir,
        ),
    )


def test_clean_successful_run_finds_one_opportunity() -> None:
    result = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    assert result.counters.goods_ids_requested == 1
    assert result.counters.goods_ids_succeeded == 1
    assert result.counters.listings_received == 10
    assert result.counters.candidate_accepted == 10
    assert result.counters.metadata_resolved == 10
    assert result.counters.input_items_created == 10
    assert result.counters.recipes_evaluated == 1
    assert result.counters.opportunities_found == 1
    assert len(result.opportunities) == 1
    assert result.opportunities[0].risk_decision.passed is True


def test_zero_listings_returns_zero_opportunities() -> None:
    provider = FakeListingProvider(listings_by_goods={GOODS_ID: []})
    result = asyncio.run(_orchestrator(provider=provider).run_once([GOODS_ID]))
    assert result.counters.listings_received == 0
    assert result.counters.opportunities_found == 0


def test_one_goods_failure_other_succeeds() -> None:
    provider = FakeListingProvider(fail_goods={"bad"})
    result = asyncio.run(_orchestrator(provider=provider).run_once(["bad", GOODS_ID]))
    assert result.counters.goods_ids_requested == 2
    assert result.counters.goods_ids_failed == 1
    assert result.counters.goods_ids_succeeded == 1
    assert result.counters.opportunities_found == 1


def test_identity_unresolved_leads_to_intrinsic_and_metadata_rejection() -> None:
    result = asyncio.run(
        _orchestrator(identity=FakeIdentityResolver(unresolved=True)).run_once([GOODS_ID])
    )
    assert result.counters.identity_unresolved == 10
    assert result.counters.intrinsic_unresolved == 10
    assert result.counters.metadata_unresolved == 10
    assert result.counters.opportunities_found == 0


def test_metadata_unresolved_is_counted() -> None:
    metadata = PinnedSkinMetadataResolver.from_payload({"items": []})
    result = asyncio.run(_orchestrator(metadata=metadata).run_once([GOODS_ID]))
    assert result.counters.metadata_resolved == 0
    assert result.counters.metadata_unresolved == 10


def test_zero_valuation_rejects_recipe() -> None:
    result = asyncio.run(_orchestrator(with_valuation=False).run_once([GOODS_ID]))
    assert result.counters.recipes_evaluated == 1
    assert result.counters.opportunities_found == 0
    assert result.counters.valuation_requests_attempted == 1
    assert result.counters.valuation_requests_succeeded == 0
    assert result.counters.valuation_requests_failed == 1
    assert result.counters.valuation_requests_blocked == 0
    assert result.counters.live_demand == 0
    assert result.counters.live_attempted == 0
    assert result.counters.live_succeeded == 0
    assert result.counters.live_failed == 0
    assert result.counters.live_atomically_blocked == 0
    assert result.counters.run_reuse_hits == 0
    assert result.recipe_evaluations[0].rejection_reason == (
        "VALUATION_SERVICE_NOT_CONFIGURED"
    )


def test_risk_rejection_counts_zero_opportunities() -> None:
    result = asyncio.run(
        _orchestrator(min_expected_profit=Decimal("999999")).run_once([GOODS_ID])
    )
    assert result.counters.opportunities_found == 0
    assert result.counters.recipes_rejected >= 1


def test_output_ordering_is_deterministic() -> None:
    first = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    second = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    assert [opp.metrics for opp in first.opportunities] == [
        opp.metrics for opp in second.opportunities
    ]


def test_goods_id_deduplication_preserves_order() -> None:
    provider = FakeListingProvider()
    orchestrator = _orchestrator(provider=provider)
    result = asyncio.run(orchestrator.run_once([GOODS_ID, GOODS_ID]))
    assert result.goods_ids == (GOODS_ID,)
    assert provider.calls == [GOODS_ID]


def test_goods_id_hard_max_fails_closed() -> None:
    goods_ids = [str(index) for index in range(11)]
    with pytest.raises(ValueError, match="hard maximum"):
        asyncio.run(_orchestrator().run_once(goods_ids))


def test_memory_error_propagates_verbatim() -> None:
    provider = FakeListingProvider(memory_error=True)
    with pytest.raises(MemoryError, match="sentinel"):
        asyncio.run(_orchestrator(provider=provider).run_once([GOODS_ID]))


def test_float_conversion_occurs_in_enrichment() -> None:
    result = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    item = result.opportunities[0].recipe.recipe.input_items[0]
    assert type(item.actual_float) is float


def test_pinned_full_seam_to_existing_solver_boundary() -> None:
    """Pinned/static integration:

    BuffListing → identity → intrinsic → adapter → metadata enrichment
    → InputItem → existing recipe solver. No network.
    """
    from pathlib import Path

    from app.services.buff_community_identity_resolver import (
        BuffCommunityIdentityResolver,
    )

    identity_path = Path("data/identity/buff_identity_v1.json")
    metadata_path = Path("data/metadata/skin_metadata_v1.json")
    if not identity_path.exists() or not metadata_path.exists():
        pytest.skip("pinned snapshots not present")

    provider = FakeListingProvider()
    identity = BuffCommunityIdentityResolver.from_snapshot_path(identity_path)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(metadata_path)
    result = asyncio.run(
        LiveScannerOrchestrator(
            listing_provider=provider,  # type: ignore[arg-type]
            identity_resolver=identity,
            metadata_resolver=metadata,
            valuation_service=None,
            max_valuation_requests_per_run=10,
            solver_config=RecipeSolverConfig(
                input_rarity="Classified",
                input_count=10,
                sell_fee_rate=Decimal("0"),
            ),
            risk_config=RiskFilterConfig(
                min_roi=Decimal("-1"),
                min_expected_profit_cny=Decimal("-1000"),
                max_worst_case_loss_pct=Decimal("1"),
                min_profit_probability=0.0,
                max_input_total_cost_cny=Decimal("999999"),
            ),
        ).run_once([GOODS_ID])
    )
    assert result.counters.goods_ids_succeeded == 1
    assert result.counters.identity_resolved == 10
    assert result.counters.intrinsic_resolved == 10
    assert result.counters.candidate_accepted == 10
    assert result.counters.metadata_resolved == 10
    assert result.counters.input_items_created == 10
    assert result.counters.recipes_evaluated >= 1
    # No valuation_service => no accepted opportunity, by design.
    assert result.counters.opportunities_found == 0


def test_metadata_intrinsic_conflict_fails_closed() -> None:
    """Metadata may not override candidate-owned intrinsic flags."""
    metadata = PinnedSkinMetadataResolver.from_payload(
        {
            "items": [
                {
                    "market_hash_name": INPUT_NAME,
                    "collection_name": "Test Collection",
                    "rarity": "Restricted",
                    "min_float": 0.10,
                    "max_float": 0.70,
                    "name": "AK-47 | Redline",
                    "weapon": "AK-47",
                    "category": "Rifle",
                    "stattrak": True,  # conflicts with canonical candidate False
                    "souvenir": False,
                    "paint_index": 282,
                },
                {
                    "market_hash_name": OUTPUT_NAME,
                    "collection_name": "Test Collection",
                    "rarity": "Classified",
                    "min_float": 0.00,
                    "max_float": 0.08,
                    "name": "M4A4 | Asiimov",
                    "weapon": "M4A4",
                    "category": "Rifle",
                    "stattrak": False,
                    "souvenir": False,
                    "paint_index": 255,
                },
            ]
        }
    )
    with pytest.raises(ValueError, match="invalid scanner recipe composition"):
        asyncio.run(_orchestrator(metadata=metadata).run_once([GOODS_ID]))


def test_valuation_request_cap_exact_boundary() -> None:
    result = asyncio.run(
        _orchestrator(max_valuation_requests=1).run_once([GOODS_ID])
    )
    assert result.counters.valuation_requests_attempted == 1
    assert result.counters.valuation_requests_blocked == 0
    assert result.counters.valuation_requests_succeeded == 1
    assert result.counters.opportunities_found == 1


def test_valuation_request_cap_exceeded_fails_closed() -> None:
    metadata = PinnedSkinMetadataResolver.from_payload(
        {
            "items": [
                _metadata_row(INPUT_NAME, "Restricted"),
                _metadata_row(OUTPUT_NAME, "Classified"),
                _metadata_row("USP-S | Orion (Factory New)", "Classified"),
            ]
        }
    )
    result = asyncio.run(
        _orchestrator(
            metadata=metadata,
            max_valuation_requests=1,
        ).run_once([GOODS_ID])
    )
    assert result.counters.valuation_requests_attempted == 0
    assert result.counters.valuation_requests_blocked == 2
    assert result.counters.recipes_valuation_failed == 1
    assert result.counters.opportunities_found == 0
    assert result.recipe_evaluations[0].rejection_reason == (
        "VALUATION_REQUEST_CAP_EXCEEDED"
    )


def test_incomplete_valuation_cannot_produce_opportunity() -> None:
    missing_provider = MockPriceProvider({}, fail_on_single_missing=False)
    result = asyncio.run(
        _orchestrator(price_provider=missing_provider).run_once([GOODS_ID])
    )
    assert result.counters.recipes_evaluated == 1
    assert result.counters.recipes_fully_valued == 0
    assert result.counters.recipes_valuation_failed == 1
    assert result.counters.valuation_requests_attempted == 1
    assert result.counters.valuation_requests_succeeded == 0
    assert result.counters.valuation_requests_failed == 1
    assert result.counters.opportunities_found == 0
    assert result.recipe_evaluations[0].valuation_completed is False


def test_complete_valuation_risk_passed_produces_opportunity() -> None:
    result = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    assert result.counters.recipes_fully_valued == 1
    assert result.recipe_evaluations[0].valuation_completed is True
    assert result.recipe_evaluations[0].risk_decision is not None
    assert result.recipe_evaluations[0].risk_decision.passed is True
    assert result.counters.opportunities_found == 1


def test_complete_valuation_risk_failed_produces_no_opportunity() -> None:
    result = asyncio.run(
        _orchestrator(min_expected_profit=Decimal("999999")).run_once([GOODS_ID])
    )
    assert result.counters.recipes_fully_valued == 1
    assert result.recipe_evaluations[0].valuation_completed is True
    assert result.recipe_evaluations[0].risk_decision is not None
    assert result.recipe_evaluations[0].risk_decision.passed is False
    assert result.counters.opportunities_found == 0


def test_valuation_memory_error_propagates_verbatim() -> None:
    class MemoryPriceProvider(MockPriceProvider):
        async def get_prices(self, market_hash_names: list[str]):  # type: ignore[no-untyped-def]
            raise MemoryError("valuation sentinel")

    with pytest.raises(MemoryError, match="valuation sentinel"):
        asyncio.run(
            _orchestrator(price_provider=MemoryPriceProvider()).run_once([GOODS_ID])
        )


def test_currency_and_unit_invariants() -> None:
    result = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    metrics = result.recipe_evaluations[0].metrics
    assert metrics is not None
    assert isinstance(metrics.input_total_cost_cny, Decimal)
    assert isinstance(metrics.expected_revenue_cny, Decimal)
    assert isinstance(metrics.expected_profit_cny, Decimal)
    assert isinstance(metrics.roi, Decimal)
    assert metrics.input_total_cost_cny > 0


def test_cap_validation_rejects_zero_and_over_policy_limit() -> None:
    with pytest.raises(ValueError, match=r"\[1, 60\]"):
        _orchestrator(max_valuation_requests=0)
    with pytest.raises(ValueError, match=r"\[1, 60\]"):
        _orchestrator(max_valuation_requests=61)
def _metadata_row(name: str, rarity: str) -> dict[str, object]:
    return {
        "market_hash_name": name,
        "collection_name": "Test Collection",
        "rarity": rarity,
        "min_float": 0.00 if rarity == "Classified" else 0.10,
        "max_float": 0.08 if rarity == "Classified" else 0.70,
        "name": name.split(" (")[0],
        "weapon": "Test Weapon",
        "category": "Rifle",
        "stattrak": False,
        "souvenir": False,
        "paint_index": 1,
    }


class MappingIntrinsicResolver:
    def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
        return BuffListingIntrinsicFlagsValue(
            stattrak=market_hash_name.startswith("StatTrak™ "),
            souvenir=market_hash_name.startswith("Souvenir "),
        )


def _mixed_metadata_resolver() -> PinnedSkinMetadataResolver:
    return PinnedSkinMetadataResolver.from_payload(
        {
            "items": [
                {
                    **_metadata_row(INPUT_NAME, "Restricted"),
                    "stattrak": False,
                    "souvenir": False,
                },
                {
                    **_metadata_row(
                        "Souvenir AK-47 | Redline (Field-Tested)",
                        "Restricted",
                    ),
                    "stattrak": False,
                    "souvenir": True,
                },
                _metadata_row(OUTPUT_NAME, "Classified"),
                {
                    **_metadata_row(
                        "Souvenir M4A4 | Asiimov (Factory New)",
                        "Classified",
                    ),
                    "stattrak": False,
                    "souvenir": True,
                },
            ]
        }
    )


def _mixed_run_inputs() -> tuple[
    FakeListingProvider,
    FakeIdentityResolver,
    PinnedSkinMetadataResolver,
]:
    normal_goods = GOODS_ID
    souvenir_goods = "souvenir-goods"
    provider = FakeListingProvider(
        listings_by_goods={
            normal_goods: [
                BuffListing(
                    listing_id=f"normal-{index}",
                    goods_id=normal_goods,
                    market_hash_name=None,
                    price_cny=Decimal("10") + Decimal(index) / Decimal("100"),
                    paintwear=Decimal("0.15"),
                    asset_id=f"normal-asset-{index}",
                    paintseed=index,
                    source="buff",
                )
                for index in range(5)
            ],
            souvenir_goods: [
                BuffListing(
                    listing_id=f"souvenir-{index}",
                    goods_id=souvenir_goods,
                    market_hash_name=None,
                    price_cny=Decimal("11") + Decimal(index) / Decimal("100"),
                    paintwear=Decimal("0.15"),
                    asset_id=f"souvenir-asset-{index}",
                    paintseed=100 + index,
                    source="buff",
                )
                for index in range(5)
            ],
        }
    )
    identity = FakeIdentityResolver(
        names_by_goods={
            normal_goods: INPUT_NAME,
            souvenir_goods: "Souvenir AK-47 | Redline (Field-Tested)",
        }
    )
    return provider, identity, _mixed_metadata_resolver()


def test_run_wide_pool_allows_normal_and_souvenir_inputs_together() -> None:
    provider, identity, metadata = _mixed_run_inputs()
    price_provider = MockPriceProvider(
        {
            OUTPUT_NAME: PriceQuote(
                market_hash_name=OUTPUT_NAME,
                price_cny=Decimal("200"),
                source="test",
            )
        }
    )
    result = asyncio.run(
        _orchestrator(
            provider=provider,
            identity=identity,
            metadata=metadata,
            price_provider=price_provider,
            intrinsic_resolver=MappingIntrinsicResolver(),
        ).run_once([GOODS_ID, "souvenir-goods"])
    )

    assert result.counters.input_items_created == 10
    assert result.counters.recipes_evaluated == 1
    evaluation = result.recipe_evaluations[0]
    assert evaluation.output_market_hash_names_requested == (OUTPUT_NAME,)
    assert [item.souvenir for item in evaluation.recipe.recipe.input_items].count(True) == 5
    assert [listing.souvenir for listing in evaluation.listings].count(True) == 5
    assert set(evaluation.recipe.selected_listing_ids) == {
        *(f"normal-{index}" for index in range(5)),
        *(f"souvenir-{index}" for index in range(5)),
    }


def test_risk_filter_sees_rehydrated_souvenir_input_facts() -> None:
    provider, identity, metadata = _mixed_run_inputs()
    price_provider = MockPriceProvider(
        {
            OUTPUT_NAME: PriceQuote(
                market_hash_name=OUTPUT_NAME,
                price_cny=Decimal("200"),
                source="test",
            )
        }
    )
    result = asyncio.run(
        _orchestrator(
            provider=provider,
            identity=identity,
            metadata=metadata,
            price_provider=price_provider,
            exclude_souvenir=True,
            intrinsic_resolver=MappingIntrinsicResolver(),
        ).run_once([GOODS_ID, "souvenir-goods"])
    )

    decision = result.recipe_evaluations[0].risk_decision
    assert decision is not None
    assert SOUVENIR_EXCLUDED in decision.reason_codes
    assert result.counters.opportunities_found == 0


def test_duplicate_listing_id_across_goods_pages_fails_closed() -> None:
    provider = FakeListingProvider(
        listings_by_goods={
            GOODS_ID: [_listing(0)],
            "other": [
                BuffListing(
                    listing_id="listing-0",
                    goods_id="other",
                    market_hash_name=None,
                    price_cny=Decimal("10"),
                    paintwear=Decimal("0.15"),
                    asset_id="other-asset",
                    paintseed=None,
                    source="buff",
                )
            ],
        }
    )
    identity = FakeIdentityResolver(
        names_by_goods={GOODS_ID: INPUT_NAME, "other": INPUT_NAME}
    )

    with pytest.raises(ValueError, match="duplicate listing_id"):
        asyncio.run(
            _orchestrator(provider=provider, identity=identity).run_once(
                [GOODS_ID, "other"]
            )
        )


def test_recipe_composition_memory_error_propagates_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = MemoryError("composition sentinel")

    def fail(**kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        fail,
    )

    with pytest.raises(MemoryError) as exc_info:
        asyncio.run(_orchestrator().run_once([GOODS_ID]))

    assert exc_info.value is sentinel


def test_repeatability() -> None:
    a = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    b = asyncio.run(_orchestrator().run_once([GOODS_ID]))
    assert a.counters == b.counters
    assert a.diagnostics == b.diagnostics
    assert a.opportunities == b.opportunities


OUTPUT_B = "USP-S | Orion (Factory New)"
OUTPUT_C = "AWP | BOOM (Factory New)"


def _controlled_selection(
    listing_indexes: tuple[int, ...],
    output_names: tuple[str, ...],
    *,
    souvenir: bool = False,
) -> ConstructedRecipeSelection:
    probabilities = [1.0 / len(output_names)] * len(output_names)
    if len(output_names) == 3:
        probabilities = [0.25, 0.25, 0.5]
    return ConstructedRecipeSelection(
        recipe=ConstructedRecipe(
            input_items=tuple(
                InputItem(
                    market_hash_name=INPUT_NAME,
                    collection_name="Test Collection",
                    rarity="Restricted",
                    actual_float=0.15,
                    min_float=0.10,
                    max_float=0.70,
                    price_cny=Decimal("10"),
                    souvenir=souvenir,
                )
                for _ in listing_indexes
            ),
            tradeup_results=tuple(
                TradeupResult(
                    output_market_hash_name=name,
                    probability=probability,
                    output_float=0.05,
                    output_wear="Factory New",
                    estimated_price_cny=Decimal("0"),
                    expected_value_contribution=Decimal("0"),
                )
                for name, probability in zip(
                    output_names,
                    probabilities,
                    strict=True,
                )
            ),
            paint_seeds=(),
        ),
        selected_listing_ids=tuple(
            f"listing-{index}" for index in listing_indexes
        ),
    )


def _composition_result(
    selections: tuple[ConstructedRecipeSelection, ...],
    *,
    states_explored: int | None = None,
    active_bucket_count: int = 1,
    participating_bucket_count: int = 1,
    aggregate_candidate_limit: int | None = None,
) -> ScannerRecipeCompositionResult:
    returned = len(selections)
    candidate_limit = aggregate_candidate_limit or max(1, returned)
    states = states_explored if states_explored is not None else returned
    if active_bucket_count == 0:
        buckets: tuple[ScannerRecipeBucketDiagnostics, ...] = ()
    elif active_bucket_count == 1:
        buckets = (
            ScannerRecipeBucketDiagnostics(
                stattrak=False,
                candidate_quota=candidate_limit,
                state_quota=max(candidate_limit, states),
                returned_candidates=returned,
                states_explored=states,
                baseline_state_rejected=False,
            ),
        )
    else:
        first_returned = min(1, returned)
        buckets = (
            ScannerRecipeBucketDiagnostics(
                stattrak=False,
                candidate_quota=1,
                state_quota=max(1, states // 2 + states % 2),
                returned_candidates=first_returned,
                states_explored=states // 2 + states % 2,
                baseline_state_rejected=False,
            ),
            ScannerRecipeBucketDiagnostics(
                stattrak=True,
                candidate_quota=max(0, candidate_limit - 1),
                state_quota=states // 2,
                returned_candidates=returned - first_returned,
                states_explored=states // 2,
                baseline_state_rejected=False,
            ),
        )
    return ScannerRecipeCompositionResult(
        selections=selections,
        diagnostics=ScannerRecipeCompositionDiagnostics(
            aggregate_candidate_limit=candidate_limit,
            aggregate_state_limit=max(candidate_limit, states, 1),
            active_bucket_count=active_bucket_count,
            participating_bucket_count=participating_bucket_count,
            buckets=buckets,
            returned_candidates=returned,
            states_explored=states,
        ),
    )


def _listing_provider(count: int = 12) -> FakeListingProvider:
    return FakeListingProvider(
        listings_by_goods={GOODS_ID: [_listing(index) for index in range(count)]}
    )


def test_generic_cached_resolver_cannot_enter_public_orchestrator_api() -> None:
    generic = SteamDTCachedPriceResolver(InMemoryPriceCache())

    with pytest.raises(TypeError, match="ScannerCachedBuffPriceResolver"):
        _orchestrator(
            cached_price_resolver=generic,  # type: ignore[arg-type]
        )


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _populate_fresh_cache(
    cache: InMemoryPriceCache,
    names: tuple[str, ...],
    *,
    now: datetime,
    non_buff_names: frozenset[str] = frozenset(),
) -> None:
    for name in names:
        platform = "Steam" if name in non_buff_names else "BUFF"
        await cache.put(
            CachedPriceSnapshot(
                key=PriceCacheKey(market_hash_name=name),
                candidates=(
                    NormalizedPriceCandidate(
                        platform=platform,
                        platform_item_id=f"{platform}-id",
                        sell_price_cny=Decimal("200"),
                        sell_count=10,
                        bidding_price_cny=Decimal("199"),
                        bidding_count=10,
                        source_update_time="opaque",
                    ),
                ),
                observed_at=now - timedelta(seconds=1),
                stored_at=now - timedelta(seconds=1),
                policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
            )
        )


def _strict_cached_resolver(cache: InMemoryPriceCache) -> ScannerCachedBuffPriceResolver:
    return ScannerCachedBuffPriceResolver(cache)


class RecordingPriceProvider(MockPriceProvider):
    def __init__(self, names: tuple[str, ...]) -> None:
        super().__init__(
            {
                name: PriceQuote(
                    market_hash_name=name,
                    price_cny=Decimal("200"),
                    source="test",
                )
                for name in names
            }
        )
        self.calls: list[tuple[str, ...]] = []

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        self.calls.append(tuple(market_hash_names))
        return await super().get_prices(market_hash_names)


def test_enumeration_config_defaults_and_explicit_dependency_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[RecipeEnumerationConfig] = []

    def compose(**kwargs):  # type: ignore[no-untyped-def]
        config = kwargs["enumeration_config"]
        seen.append(config)
        return _composition_result(
            (),
            states_explored=0,
            active_bucket_count=0,
            participating_bucket_count=0,
            aggregate_candidate_limit=config.max_recipe_candidates_returned,
        )

    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        compose,
    )
    asyncio.run(
        _orchestrator(
            provider=FakeListingProvider(listings_by_goods={GOODS_ID: []})
        ).run_once([GOODS_ID])
    )
    explicit = RecipeEnumerationConfig(
        max_recipe_candidates_returned=1,
        max_candidate_states_explored=1,
    )
    asyncio.run(
        _orchestrator(
            provider=FakeListingProvider(listings_by_goods={GOODS_ID: []}),
            enumeration_config=explicit,
        ).run_once([GOODS_ID])
    )

    assert seen[0] == RecipeEnumerationConfig(
        max_recipe_candidates_returned=2,
        max_candidate_states_explored=256,
    )
    assert seen[1] == explicit
    assert seen[1] is not explicit


def test_one_recipe_bounded_compatibility() -> None:
    result = asyncio.run(
        _orchestrator(
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=1,
                max_candidate_states_explored=1,
            )
        ).run_once([GOODS_ID])
    )

    assert result.counters.recipes_evaluated == 1
    assert result.counters.recipes_fully_valued == 1
    assert result.counters.valuation_requests_attempted == 1
    assert result.counters.valuation_requests_succeeded == 1
    assert result.counters.recipes_rejected == 0
    assert result.counters.opportunities_found == 1
    assert result.opportunities[0].recipe.selected_listing_ids == tuple(
        f"listing-{index}" for index in range(10)
    )
    assert result.opportunities[0].metrics == result.recipe_evaluations[0].metrics
    assert result.diagnostics.recipe_composition is not None
    assert result.diagnostics.recipe_composition.aggregate_candidate_limit == 1
    assert result.diagnostics.recipe_composition.aggregate_state_limit == 1


def test_multi_recipe_happy_path_processes_every_selection_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_B,)),
    )
    composition_calls: list[dict[str, object]] = []

    def compose(**kwargs):  # type: ignore[no-untyped-def]
        composition_calls.append(kwargs)
        return _composition_result(selections, aggregate_candidate_limit=2)

    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        compose,
    )
    price_provider = RecordingPriceProvider((OUTPUT_NAME, OUTPUT_B))
    metrics_calls: list[tuple[InputItem, ...]] = []
    risk_calls: list[tuple[InputItem, ...]] = []
    from app.services import scanner_orchestrator as orchestrator_module

    calculate_metrics = orchestrator_module.calculate_opportunity_metrics
    evaluate_risk = orchestrator_module.evaluate_opportunity

    def metrics(*args, **kwargs):  # type: ignore[no-untyped-def]
        input_items = args[0] if args else kwargs["input_items"]
        metrics_calls.append(tuple(input_items))
        return calculate_metrics(*args, **kwargs)

    def risk(*args, **kwargs):  # type: ignore[no-untyped-def]
        input_items = args[1] if args else kwargs["input_items"]
        risk_calls.append(tuple(input_items))
        return evaluate_risk(*args, **kwargs)

    monkeypatch.setattr(orchestrator_module, "calculate_opportunity_metrics", metrics)
    monkeypatch.setattr(orchestrator_module, "evaluate_opportunity", risk)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
        ).run_once([GOODS_ID])
    )

    assert len(composition_calls) == 1
    assert price_provider.calls == [(OUTPUT_NAME,), (OUTPUT_B,)]
    assert len(metrics_calls) == 2
    assert len(risk_calls) == 2
    assert result.counters.recipes_evaluated == 2
    assert result.counters.recipes_fully_valued == 2
    assert result.counters.opportunities_found == 2
    assert [
        opportunity.recipe.selected_listing_ids for opportunity in result.opportunities
    ] == [selection.selected_listing_ids for selection in selections]
    assert result.recipe_evaluations[0].listings[0] is result.recipe_evaluations[1].listings[0]


def test_mixed_risk_results_process_all_candidates_and_keep_passed_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 11), (OUTPUT_NAME,)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=3,
        ),
    )
    decisions = iter((False, True, True))
    risk_calls: list[bool] = []

    def risk(*args, **kwargs):  # type: ignore[no-untyped-def]
        passed = next(decisions)
        risk_calls.append(passed)
        return RiskDecision(
            passed=passed,
            reasons=[] if passed else ["rejected"],
            reason_codes=[] if passed else ["TEST_REJECTION"],
            risk_score=Decimal("0") if passed else Decimal("1"),
        )

    monkeypatch.setattr(
        "app.services.scanner_orchestrator.evaluate_opportunity",
        risk,
    )
    price_provider = RecordingPriceProvider((OUTPUT_NAME,))
    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=3,
                max_candidate_states_explored=3,
            ),
        ).run_once([GOODS_ID])
    )

    # Phase 14B: identical OUTPUT_NAME across all 3 selections is memoed
    # after Recipe 0; only Recipe 0 hits the live provider. Recipes 1 and 2
    # reuse the memoed success.
    assert risk_calls == [False, True, True]
    assert price_provider.calls == [(OUTPUT_NAME,)]
    assert result.counters.recipes_evaluated == 3
    assert result.counters.recipes_fully_valued == 3
    assert result.counters.recipes_rejected == 1
    assert result.counters.live_attempted == 1
    assert result.counters.live_succeeded == 1
    assert result.counters.live_demand == 1
    assert result.counters.run_reuse_hits == 2
    assert result.counters.run_reuse_successes == 2
    assert result.counters.run_reuse_failures == 0
    assert [
        opportunity.recipe.selected_listing_ids for opportunity in result.opportunities
    ] == [
        selections[1].selected_listing_ids,
        selections[2].selected_listing_ids,
    ]


def test_incomplete_recipe_valuation_skips_metrics_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_NAME,)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )

    class FirstMissingPriceProvider(RecordingPriceProvider):
        async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
            self.calls.append(tuple(market_hash_names))
            if len(self.calls) == 1:
                return PriceLookupResult(
                    quotes={},
                    missing=list(market_hash_names),
                    errors=[],
                )
            return await MockPriceProvider.get_prices(self, market_hash_names)

    price_provider = FirstMissingPriceProvider((OUTPUT_NAME,))
    metrics_calls: list[int] = []
    risk_calls: list[int] = []
    from app.services import scanner_orchestrator as orchestrator_module

    calculate_metrics = orchestrator_module.calculate_opportunity_metrics
    evaluate_risk = orchestrator_module.evaluate_opportunity

    def metrics(*args, **kwargs):  # type: ignore[no-untyped-def]
        metrics_calls.append(1)
        return calculate_metrics(*args, **kwargs)

    def risk(*args, **kwargs):  # type: ignore[no-untyped-def]
        risk_calls.append(1)
        return evaluate_risk(*args, **kwargs)

    monkeypatch.setattr(orchestrator_module, "calculate_opportunity_metrics", metrics)
    monkeypatch.setattr(orchestrator_module, "evaluate_opportunity", risk)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
        ).run_once([GOODS_ID])
    )

    # Phase 14B: Recipe 0's terminal failure is memoed; Recipe 1 reuses
    # the failure (no second provider call). Neither recipe completes,
    # so metrics/risk are never invoked.
    assert price_provider.calls == [(OUTPUT_NAME,)]
    assert metrics_calls == []
    assert risk_calls == []
    assert result.counters.recipes_evaluated == 2
    assert result.counters.recipes_fully_valued == 0
    assert result.counters.recipes_valuation_failed == 2
    assert result.counters.recipes_rejected == 2
    assert result.counters.opportunities_found == 0
    assert result.counters.live_attempted == 1
    assert result.counters.live_failed == 1
    assert result.counters.run_reuse_hits == 1
    assert result.counters.run_reuse_failures == 1
    assert result.recipe_evaluations[0].valuation_completed is False
    assert result.recipe_evaluations[1].valuation_completed is False


@pytest.mark.parametrize(
    (
        "cap",
        "expected_calls",
        "attempted",
        "blocked",
        "fully_valued",
        "live_demand",
        "live_attempted",
        "live_succeeded",
        "run_reuse_hits",
    ),
    [
        # cap=4: each recipe's NEW LIVE fits within cap; both admitted.
        # Recipe 0 needs {NAME, B}; Recipe 1 needs only {C} (NAME memoed).
        (4, [(OUTPUT_NAME, OUTPUT_B), (OUTPUT_C,)], 4, 0, 2, 3, 3, 3, 1),
        # cap=3: Recipe 0 needs 2, Recipe 1 needs 1 NEW LIVE; both fit.
        (3, [(OUTPUT_NAME, OUTPUT_B), (OUTPUT_C,)], 4, 0, 2, 3, 3, 3, 1),
        # cap=2: Recipe 0 admitted (2 NEW LIVE). Recipe 1 would need
        # 1 more; 2 + 1 = 3 > 2 blocked atomically. Recipe 1 saw NAME
        # as a memo hit, so run_reuse_hits = 1.
        (2, [(OUTPUT_NAME, OUTPUT_B)], 2, 2, 1, 3, 2, 2, 1),
        # cap=1: Recipe 0 itself would need 2 NEW LIVE; 2 > 1 blocked.
        # Recipe 1's prepare sees Recipe 0's blocked names as NEW LIVE
        # again (not memoed) and is also blocked.
        (1, [], 0, 4, 0, 4, 0, 0, 0),
    ],
)
def test_cumulative_valuation_cap_uses_per_recipe_exact_name_requests(
    monkeypatch: pytest.MonkeyPatch,
    cap: int,
    expected_calls: list[tuple[str, ...]],
    attempted: int,
    blocked: int,
    fully_valued: int,
    live_demand: int,
    live_attempted: int,
    live_succeeded: int,
    run_reuse_hits: int,
) -> None:
    selections = (
        _controlled_selection(
            tuple(range(10)),
            (OUTPUT_NAME, OUTPUT_NAME, OUTPUT_B),
        ),
        _controlled_selection((*range(9), 10), (OUTPUT_NAME, OUTPUT_C)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    price_provider = RecordingPriceProvider((OUTPUT_NAME, OUTPUT_B, OUTPUT_C))

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
            max_valuation_requests=cap,
        ).run_once([GOODS_ID])
    )

    assert price_provider.calls == expected_calls
    assert result.counters.valuation_requests_attempted == attempted
    assert result.counters.valuation_requests_blocked == blocked
    assert result.counters.recipes_fully_valued == fully_valued
    # Each blocked recipe has requested_count=2 in this fixture, so the
    # number of blocked recipes equals blocked // 2.
    assert result.counters.recipes_valuation_failed == (blocked // 2)
    assert result.counters.live_demand == live_demand
    assert result.counters.live_attempted == live_attempted
    assert result.counters.live_succeeded == live_succeeded
    assert result.counters.run_reuse_hits == run_reuse_hits
    if blocked:
        assert any(
            evaluation.rejection_reason == "VALUATION_REQUEST_CAP_EXCEEDED"
            for evaluation in result.recipe_evaluations
        )


def test_empty_bounded_composition_skips_all_recipe_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _composition_result(
        (),
        states_explored=0,
        active_bucket_count=0,
        participating_bucket_count=0,
        aggregate_candidate_limit=2,
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: composition,  # type: ignore[no-untyped-def]
    )

    async def fail_valuation(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("valuation must not run")

    monkeypatch.setattr(
        ValuationService,
        "value_tradeup_results",
        fail_valuation,
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.calculate_opportunity_metrics",
        lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[no-untyped-def]
            AssertionError("metrics must not run")
        ),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.evaluate_opportunity",
        lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[no-untyped-def]
            AssertionError("risk must not run")
        ),
    )

    result = asyncio.run(_orchestrator().run_once([GOODS_ID]))

    assert result.counters.recipes_evaluated == 0
    assert result.counters.valuation_requests_attempted == 0
    assert result.counters.opportunities_found == 0
    assert result.recipe_evaluations == ()
    assert result.diagnostics.recipe_composition == composition.diagnostics


def test_composition_diagnostics_are_preserved_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_B,)),
    )
    composition = _composition_result(
        selections,
        states_explored=17,
        active_bucket_count=2,
        participating_bucket_count=2,
        aggregate_candidate_limit=2,
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: composition,  # type: ignore[no-untyped-def]
    )

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=RecordingPriceProvider((OUTPUT_NAME, OUTPUT_B)),
        ).run_once([GOODS_ID])
    )

    assert result.diagnostics.recipe_composition is composition.diagnostics
    diagnostics = result.diagnostics.recipe_composition
    assert diagnostics is not None
    assert diagnostics.active_bucket_count == 2
    assert diagnostics.participating_bucket_count == 2
    assert diagnostics.returned_candidates == 2
    assert diagnostics.states_explored == 17


def test_rehydrated_souvenir_inputs_reach_orchestrator_valuation_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, identity, metadata = _mixed_run_inputs()
    orchestrator = _orchestrator(
        provider=provider,
        identity=identity,
        metadata=metadata,
        price_provider=RecordingPriceProvider((OUTPUT_NAME,)),
        intrinsic_resolver=MappingIntrinsicResolver(),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=1,
        ),
    )
    original_evaluate = orchestrator._evaluate_selection
    observed: list[tuple[InputItem, ...]] = []

    async def observe(selection, listing_index, requested_names, session_result):  # type: ignore[no-untyped-def]
        observed.append(selection.recipe.input_items)
        return await original_evaluate(selection, listing_index, requested_names, session_result)

    monkeypatch.setattr(orchestrator, "_evaluate_selection", observe)
    result = asyncio.run(orchestrator.run_once([GOODS_ID, "souvenir-goods"]))

    assert len(observed) == 1
    assert sum(item.souvenir for item in observed[0]) == 5
    assert observed[0] == result.recipe_evaluations[0].recipe.recipe.input_items
    assert any(item.souvenir for item in observed[0])


def test_composition_unexpected_exception_propagates_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("composition sentinel")

    def fail(**kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        fail,
    )
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_orchestrator().run_once([GOODS_ID]))
    assert exc_info.value is sentinel


def test_valuation_unexpected_exception_propagates_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _controlled_selection(tuple(range(10)), (OUTPUT_NAME,))
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            (selection,),
            aggregate_candidate_limit=1,
        ),
    )
    orchestrator = _orchestrator(
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=1,
        )
    )
    sentinel = RuntimeError("valuation sentinel")

    async def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(orchestrator, "_evaluate_selection", fail)
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(orchestrator.run_once([GOODS_ID]))
    assert exc_info.value is sentinel


def test_run_scoped_session_is_recreated_for_each_run_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _controlled_selection(tuple(range(10)), (OUTPUT_NAME,))
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            (selection,),
            aggregate_candidate_limit=1,
        ),
    )
    price_provider = RecordingPriceProvider((OUTPUT_NAME,))
    orchestrator = _orchestrator(
        provider=_listing_provider(),
        price_provider=price_provider,
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=1,
        ),
    )

    first = asyncio.run(orchestrator.run_once([GOODS_ID]))
    second = asyncio.run(orchestrator.run_once([GOODS_ID]))

    assert price_provider.calls == [(OUTPUT_NAME,), (OUTPUT_NAME,)]
    for result in (first, second):
        assert result.counters.live_demand == 1
        assert result.counters.live_attempted == 1
        assert result.counters.live_succeeded == 1
        assert result.counters.run_reuse_hits == 0
        assert result.counters.cache_hits_fresh_selected == 0
        assert result.counters.cache_misses == 0
        assert result.counters.cache_policy_blocked == 0
        assert result.counters.cache_expired == 0
        assert result.counters.cache_selection_failures == 0


def test_same_output_recipes_preserve_legacy_logical_counters_and_reuse_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_names = tuple(f"Synthetic Shared Output {index}" for index in range(10))
    selections = (
        _controlled_selection(tuple(range(10)), output_names),
        _controlled_selection((*range(9), 10), output_names),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    price_provider = RecordingPriceProvider(output_names)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
            max_valuation_requests=10,
        ).run_once([GOODS_ID])
    )

    assert price_provider.calls == [output_names]
    assert result.counters.valuation_requests_attempted == 20
    assert result.counters.valuation_requests_succeeded == 20
    assert result.counters.valuation_requests_failed == 0
    assert result.counters.valuation_requests_blocked == 0
    assert result.counters.live_demand == 10
    assert result.counters.live_attempted == 10
    assert result.counters.live_succeeded == 10
    assert result.counters.live_failed == 0
    assert result.counters.live_atomically_blocked == 0
    assert result.counters.run_reuse_hits == 10
    assert result.counters.run_reuse_successes == 10
    assert result.counters.run_reuse_failures == 0
    assert result.counters.recipes_fully_valued == 2
    assert result.counters.cache_hits_fresh_selected == 0
    assert result.counters.cache_misses == 0
    assert result.counters.cache_policy_blocked == 0
    assert result.counters.cache_expired == 0
    assert result.counters.cache_selection_failures == 0
    assert (
        result.counters.run_reuse_hits
        == result.counters.run_reuse_successes
        + result.counters.run_reuse_failures
    )
    assert result.counters.live_demand == (
        result.counters.live_attempted
        + result.counters.live_atomically_blocked
    )
    assert result.counters.live_attempted == (
        result.counters.live_succeeded + result.counters.live_failed
    )


def test_same_output_recipes_one_below_cap_block_atomically_without_memo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_names = tuple(f"Synthetic Shared Output {index}" for index in range(10))
    selections = (
        _controlled_selection(tuple(range(10)), output_names),
        _controlled_selection((*range(9), 10), output_names),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    price_provider = RecordingPriceProvider(output_names)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
            max_valuation_requests=9,
        ).run_once([GOODS_ID])
    )

    assert price_provider.calls == []
    assert result.counters.valuation_requests_attempted == 0
    assert result.counters.valuation_requests_succeeded == 0
    assert result.counters.valuation_requests_failed == 0
    assert result.counters.valuation_requests_blocked == 20
    assert result.counters.live_demand == 20
    assert result.counters.live_attempted == 0
    assert result.counters.live_succeeded == 0
    assert result.counters.live_failed == 0
    assert result.counters.live_atomically_blocked == 20
    assert result.counters.run_reuse_hits == 0
    assert result.counters.recipes_fully_valued == 0
    assert result.counters.recipes_valuation_failed == 2
    assert all(
        evaluation.rejection_reason == "VALUATION_REQUEST_CAP_EXCEEDED"
        for evaluation in result.recipe_evaluations
    )




def test_all_fresh_same_output_recipes_use_cache_then_run_memo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_names = tuple(f"Cached Shared Output {index}" for index in range(10))
    selections = (
        _controlled_selection(tuple(range(10)), output_names),
        _controlled_selection((*range(9), 10), output_names),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=FixedClock(now))
    asyncio.run(_populate_fresh_cache(cache, output_names, now=now))
    provider = RecordingPriceProvider(output_names)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=provider,
            cached_price_resolver=_strict_cached_resolver(cache),
            max_valuation_requests=1,
        ).run_once([GOODS_ID])
    )

    assert provider.calls == []
    assert result.counters.valuation_requests_attempted == 20
    assert result.counters.valuation_requests_succeeded == 20
    assert result.counters.valuation_requests_failed == 0
    assert result.counters.valuation_requests_blocked == 0
    assert result.counters.cache_hits_fresh_selected == 10
    assert result.counters.cache_misses == 0
    assert result.counters.cache_selection_failures == 0
    assert result.counters.run_reuse_hits == 10
    assert result.counters.run_reuse_successes == 10
    assert result.counters.run_reuse_failures == 0
    assert result.counters.live_demand == 0
    assert result.counters.live_attempted == 0
    assert result.counters.live_succeeded == 0
    assert result.counters.live_failed == 0
    assert result.counters.live_atomically_blocked == 0
    assert result.counters.recipes_fully_valued == 2


def test_nine_fresh_one_miss_exact_live_boundary_admits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_names = tuple(f"Mixed Cached Output {index}" for index in range(10))
    selection = _controlled_selection(tuple(range(10)), output_names)
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            (selection,),
            aggregate_candidate_limit=1,
        ),
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=FixedClock(now))
    asyncio.run(_populate_fresh_cache(cache, output_names[:9], now=now))
    provider = RecordingPriceProvider(output_names)

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=provider,
            cached_price_resolver=_strict_cached_resolver(cache),
            max_valuation_requests=1,
        ).run_once([GOODS_ID])
    )

    assert provider.calls == [(output_names[9],)]
    assert result.counters.cache_hits_fresh_selected == 9
    assert result.counters.cache_misses == 1
    assert result.counters.live_demand == 1
    assert result.counters.live_attempted == 1
    assert result.counters.live_succeeded == 1
    assert result.counters.live_atomically_blocked == 0
    assert result.counters.valuation_requests_attempted == 10
    assert result.counters.valuation_requests_succeeded == 10
    assert result.counters.recipes_fully_valued == 1


def test_prior_live_use_leaves_zero_for_mixed_recipe_and_blocks_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_names = tuple(f"Blocked Cached Output {index}" for index in range(9))
    miss_name = "Blocked Cache Miss"
    selections = (
        _controlled_selection(tuple(range(10)), ("Consumes Live Cap",)),
        _controlled_selection((*range(9), 10), (*cached_names, miss_name)),
        _controlled_selection((*range(9), 11), (cached_names[0], miss_name)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=3,
        ),
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=FixedClock(now))
    asyncio.run(_populate_fresh_cache(cache, cached_names, now=now))
    provider = RecordingPriceProvider(
        ("Consumes Live Cap", *cached_names, miss_name)
    )

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=provider,
            cached_price_resolver=_strict_cached_resolver(cache),
            max_valuation_requests=1,
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=3,
                max_candidate_states_explored=3,
            ),
        ).run_once([GOODS_ID])
    )

    assert provider.calls == [("Consumes Live Cap",)]
    assert result.counters.cache_hits_fresh_selected == 9
    assert result.counters.cache_misses == 3
    assert result.counters.run_reuse_hits == 1
    assert result.counters.run_reuse_successes == 1
    assert result.counters.live_demand == 3
    assert result.counters.live_attempted == 1
    assert result.counters.live_atomically_blocked == 2
    assert result.counters.valuation_requests_attempted == 1
    assert result.counters.valuation_requests_blocked == 12
    assert result.recipe_evaluations[1].rejection_reason == (
        "VALUATION_REQUEST_CAP_EXCEEDED"
    )
    assert result.recipe_evaluations[2].rejection_reason == (
        "VALUATION_REQUEST_CAP_EXCEEDED"
    )


def test_fresh_strict_buff_selection_failure_has_no_live_or_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_NAME,)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=FixedClock(now))
    asyncio.run(
        _populate_fresh_cache(
            cache,
            (OUTPUT_NAME,),
            now=now,
            non_buff_names=frozenset({OUTPUT_NAME}),
        )
    )
    provider = RecordingPriceProvider((OUTPUT_NAME,))

    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=provider,
            cached_price_resolver=_strict_cached_resolver(cache),
            max_valuation_requests=1,
        ).run_once([GOODS_ID])
    )

    assert provider.calls == []
    assert result.counters.cache_selection_failures == 1
    assert result.counters.run_reuse_failures == 1
    assert result.counters.live_demand == 0
    assert result.counters.live_attempted == 0
    assert result.counters.recipes_fully_valued == 0
    assert result.counters.recipes_valuation_failed == 2
    assert result.counters.opportunities_found == 0
    assert all(
        not evaluation.valuation_completed
        and evaluation.metrics is None
        and evaluation.risk_decision is None
        for evaluation in result.recipe_evaluations
    )


def test_cache_fatal_error_propagates_before_live_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _controlled_selection(tuple(range(10)), (OUTPUT_NAME,))
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            (selection,),
            aggregate_candidate_limit=1,
        ),
    )
    sentinel = RuntimeError("cache fatal sentinel")

    class FailingReader:
        async def get(self, key, *, read_policy):  # type: ignore[no-untyped-def]
            raise sentinel

    resolver = ScannerCachedBuffPriceResolver(FailingReader())
    provider = RecordingPriceProvider((OUTPUT_NAME,))
    orchestrator = _orchestrator(
        provider=_listing_provider(),
        price_provider=provider,
        cached_price_resolver=resolver,
    )

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(orchestrator.run_once([GOODS_ID]))
    assert exc_info.value is sentinel
    assert provider.calls == []


def test_same_orchestrator_two_runs_rechecks_cache_then_uses_same_run_memo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), (OUTPUT_NAME,)),
        _controlled_selection((*range(9), 10), (OUTPUT_NAME,)),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=FixedClock(now))
    asyncio.run(_populate_fresh_cache(cache, (OUTPUT_NAME,), now=now))

    class CountingReader:
        def __init__(self, delegate: InMemoryPriceCache) -> None:
            self.delegate = delegate
            self.calls: list[str] = []

        async def get(self, key, *, read_policy):  # type: ignore[no-untyped-def]
            self.calls.append(key.market_hash_name)
            return await self.delegate.get(key, read_policy=read_policy)

    reader = CountingReader(cache)
    resolver = ScannerCachedBuffPriceResolver(reader)
    provider = RecordingPriceProvider((OUTPUT_NAME,))
    orchestrator = _orchestrator(
        provider=_listing_provider(),
        price_provider=provider,
        cached_price_resolver=resolver,
    )

    first = asyncio.run(orchestrator.run_once([GOODS_ID]))
    second = asyncio.run(orchestrator.run_once([GOODS_ID]))

    assert reader.calls == [OUTPUT_NAME, OUTPUT_NAME]
    assert provider.calls == []
    for result in (first, second):
        assert result.counters.cache_hits_fresh_selected == 1
        assert result.counters.run_reuse_hits == 1
        assert result.counters.run_reuse_successes == 1
        assert result.counters.live_demand == 0
        assert result.counters.live_attempted == 0
        assert result.counters.recipes_fully_valued == 2


def test_terminal_failure_reused_without_retry_through_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = (
        _controlled_selection(tuple(range(10)), ("X", "Y")),
        _controlled_selection((*range(9), 10), ("X", "Y", "Z")),
    )
    monkeypatch.setattr(
        "app.services.scanner_orchestrator.enumerate_scanner_recipe_selections",
        lambda **kwargs: _composition_result(  # type: ignore[no-untyped-def]
            selections,
            aggregate_candidate_limit=2,
        ),
    )

    class FailureReuseProvider(RecordingPriceProvider):
        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            names = tuple(market_hash_names)
            if names == ("X", "Y"):
                self.calls.append(names)
                return PriceLookupResult(
                    quotes={
                        "X": PriceQuote(
                            market_hash_name="X",
                            price_cny=Decimal("200"),
                            source="test",
                        )
                    },
                    missing=["Y"],
                    errors=["TEST_MISSING_Y"],
                )
            return await super().get_prices(market_hash_names)

    price_provider = FailureReuseProvider(("X", "Y", "Z"))
    result = asyncio.run(
        _orchestrator(
            provider=_listing_provider(),
            price_provider=price_provider,
            max_valuation_requests=3,
        ).run_once([GOODS_ID])
    )

    assert price_provider.calls == [("X", "Y"), ("Z",)]
    assert result.counters.live_demand == 3
    assert result.counters.live_attempted == 3
    assert result.counters.live_succeeded == 2
    assert result.counters.live_failed == 1
    assert result.counters.run_reuse_hits == 2
    assert result.counters.run_reuse_successes == 1
    assert result.counters.run_reuse_failures == 1
    assert result.counters.valuation_requests_attempted == 5
    assert result.counters.valuation_requests_succeeded == 3
    assert result.counters.valuation_requests_failed == 2
    assert result.counters.recipes_fully_valued == 0
    assert result.counters.opportunities_found == 0
    assert all(
        evaluation.valuation_completed is False
        and evaluation.metrics is None
        and evaluation.risk_decision is None
        for evaluation in result.recipe_evaluations
    )
