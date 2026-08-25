from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagsValue,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.buff_listing_provider import BuffListing
from app.services.price_provider import MockPriceProvider, PriceQuote
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import SOUVENIR_EXCLUDED, RiskFilterConfig
from app.services.scanner_orchestrator import LiveScannerOrchestrator
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
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
        max_valuation_requests_per_run=max_valuation_requests,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=Decimal("0"),
        ),
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
        "app.services.scanner_orchestrator.construct_scanner_recipe_selections",
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
