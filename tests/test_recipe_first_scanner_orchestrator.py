"""Phase 16E — Opt-in recipe-first orchestrator tests."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.services.buff_item_identity import BuffItemIdentity
from app.services.metadata_models import SkinMetadata
from app.services.price_provider import MockPriceProvider, PriceQuote
from app.services.recipe_family import StatTrakMode, build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.recipe_first_acquisition import (
    RecipeFirstAcquisitionPage,
    RecipeFirstAcquisitionStageCounts,
    RecipeFirstListingProvenance,
)
from app.services.recipe_first_scanner_orchestrator import (
    RecipeFirstScannerConfig,
    RecipeFirstScannerError,
    RecipeFirstScannerOrchestrator,
)
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.targeted_buff_scan_plan import (
    TargetedBuffScanDecision,
    TargetedBuffScanItem,
    TargetedBuffScanPlan,
)
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem
from app.services.valuation_service import ValuationConfig, ValuationService


def _output_rows(
    collections: tuple[str, ...], *, stattrak: bool = False
) -> list[SkinMetadata]:
    rows: list[SkinMetadata] = []
    for collection in collections:
        prefix = "StatTrak™ " if stattrak else ""
        for wear in (
            "Factory New",
            "Minimal Wear",
            "Field-Tested",
            "Well-Worn",
            "Battle-Scarred",
        ):
            rows.append(
                SkinMetadata(
                    market_hash_name=f"{prefix}{collection} Output ({wear})",
                    name=f"{prefix}{collection} Output",
                    weapon="AK-47",
                    rarity="Classified",
                    category=None,
                    collection_name=collection,
                    min_float=0.0,
                    max_float=1.0,
                    stattrak=stattrak,
                    souvenir=False,
                    paint_index=None,
                    raw=None,
                )
            )
    return rows


def _enriched(
    *,
    collection: str,
    market_hash_name: str,
    goods_id: str,
    index: int,
    stattrak: bool = False,
    souvenir: bool = False,
) -> TradeUpEnrichedInput:
    candidate = TradeUpInputCandidate(
        listing_id=f"listing-{collection}-{index}",
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal("1"),
        paintwear=Decimal("0.01"),
        asset_id=f"asset-{collection}-{index}",
        source="buff",
        stattrak=stattrak,
        souvenir=souvenir,
    )
    return TradeUpEnrichedInput(
        candidate=candidate,
        input_item=InputItem(
            market_hash_name=market_hash_name,
            collection_name=collection,
            rarity="Restricted",
            actual_float=0.01,
            min_float=0.0,
            max_float=1.0,
            price_cny=Decimal("1"),
            stattrak=stattrak,
            souvenir=souvenir,
        ),
    )


@dataclass
class FakePageProvider:
    pages: dict[str, tuple[TradeUpEnrichedInput, ...]]
    fail_goods_ids: set[str] | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def acquire_page(
        self, *, goods_id: str, market_hash_name: str
    ) -> RecipeFirstAcquisitionPage:
        self.calls.append((goods_id, market_hash_name))
        if self.fail_goods_ids and goods_id in self.fail_goods_ids:
            raise RuntimeError("fake page failure")
        enriched = self.pages.get(goods_id, ())
        provenance = tuple(
            RecipeFirstListingProvenance(
                listing_id=item.candidate.listing_id,
                goods_id=item.candidate.goods_id,
                asset_id=item.candidate.asset_id,
                market_hash_name=item.candidate.market_hash_name or "",
                price_cny=item.candidate.price_cny,
                paintwear=item.candidate.paintwear,
                paintseed=None,
                stattrak=item.candidate.stattrak or False,
                souvenir=item.candidate.souvenir or False,
                source=item.candidate.source,
            )
            for item in enriched
        )
        counts = RecipeFirstAcquisitionStageCounts(
            listings_received=len(enriched),
            identity_resolved=len(enriched),
            identity_unresolved=0,
            intrinsic_resolved=len(enriched),
            intrinsic_unresolved=0,
            candidate_accepted=len(enriched),
            candidate_rejected=0,
            metadata_resolved=len(enriched),
            metadata_unresolved=0,
        )
        return RecipeFirstAcquisitionPage(
            goods_id=goods_id,
            market_hash_name=market_hash_name,
            enriched_inputs=enriched,
            provenance=provenance,
            counts=counts,
            candidate_rejection_histogram=(),
            metadata_rejection_histogram=(),
        )


class CountingPriceProvider(MockPriceProvider):
    def __init__(self, quotes_by_name: dict[str, PriceQuote]) -> None:
        super().__init__(quotes_by_name)
        self.batch_calls: list[tuple[str, ...]] = []

    async def get_prices(self, names: list[str]):
        self.batch_calls.append(tuple(names))
        return await super().get_prices(names)


class CountingIdentityResolver:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
        self.calls.append(goods_id)
        name = self.mapping.get(goods_id)
        return (
            BuffItemIdentity(market_hash_name=name, goods_id=goods_id)
            if name is not None
            else None
        )


def _risk(*, pass_all: bool = True) -> RiskFilterConfig:
    return RiskFilterConfig(
        min_roi=Decimal("-100") if pass_all else Decimal("100"),
        min_expected_profit_cny=Decimal("-10000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("10000"),
    )


def _context(
    *,
    counts: tuple[tuple[str, int], ...] = (("A", 6), ("B", 4)),
    enabled: bool = True,
    valuation_cap: int = 60,
    page_failure: str | None = None,
    missing_output_price: bool = False,
    two_selections: bool = False,
    stattrak: bool = False,
    souvenir_mix: bool = False,
):
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=(
            StatTrakMode.STATTRAK if stattrak else StatTrakMode.NORMAL
        ),
        collection_counts=counts,
    )
    finish_index = StructuralOutputFinishIndex.from_skins(
        _output_rows(tuple(name for name, _count in counts), stattrak=stattrak)
    )
    geometry = compute_recipe_family_geometry(family, finish_index=finish_index)
    plan_items: list[TargetedBuffScanItem] = []
    pages: dict[str, tuple[TradeUpEnrichedInput, ...]] = {}
    identity: dict[str, str] = {}
    for collection_index, (collection, required) in enumerate(counts):
        name_prefix = "StatTrak™ " if stattrak else ""
        name = f"{name_prefix}{collection} Input (Factory New)"
        goods_id = f"goods-{collection}"
        identity[goods_id] = name
        plan_items.append(
            TargetedBuffScanItem(
                market_hash_name=name,
                goods_id=goods_id,
                collection_name=collection,
                collection_role=(
                    "primary" if collection_index == 0 else "secondary"
                ),
                priority_within_collection=1,
            )
        )
        count = required + (1 if two_selections and collection_index == 0 else 0)
        pages[goods_id] = tuple(
            _enriched(
                collection=collection,
                market_hash_name=name,
                goods_id=goods_id,
                index=collection_index * 100 + index,
                stattrak=stattrak,
                souvenir=(souvenir_mix and not stattrak and index % 2 == 0),
            )
            for index in range(count)
        )
    plan = TargetedBuffScanPlan(
        family_hash=family.family_hash,
        items=tuple(plan_items),
        stattrak_mode=family.stattrak_mode,
        priority=1,
        hard_request_count=len(plan_items),
        unresolved_identity_count=0,
        diagnostics=("fixture",),
    )
    decision = TargetedBuffScanDecision(
        ranked_family_keys=(family.family_key, "f" * 24),
        active_family_key=family.family_key,
        active_plan=plan,
        fallback_family_key="f" * 24,
        hard_request_cap=10,
        diagnostics=("fixture",),
    )
    output_names = tuple(
        finish_index.resolve_wear_market_hash_name(
            finish_key=outcome.finish_key,
            wear_name="Factory New",
        )
        for outcome in geometry.outcomes
    )
    quotes = {
        name: PriceQuote(
            market_hash_name=name,
            price_cny=Decimal("100"),
            source="steamdt:buff",
            raw=None,
        )
        for name in output_names
        if name is not None
    }
    if missing_output_price:
        quotes.pop(next(iter(quotes)))
    page_provider = FakePageProvider(
        pages,
        {page_failure} if page_failure else None,
    )
    price_provider = CountingPriceProvider(quotes)
    identity_resolver = CountingIdentityResolver(identity)
    orchestrator = RecipeFirstScannerOrchestrator(
        listing_provider=page_provider,
        identity_resolver=identity_resolver,
        valuation_service=ValuationService(
            price_provider,
            ValuationConfig(require_all_prices=True),
        ),
        finish_index=finish_index,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            sell_fee_rate=Decimal("0"),
            target_stattrak=stattrak,
        ),
        risk_config=_risk(),
        enumeration_config=RecipeEnumerationConfig(),
        config=RecipeFirstScannerConfig(
            enabled=enabled,
            max_valuation_requests_per_run=valuation_cap,
        ),
    )
    return (
        family,
        geometry,
        decision,
        orchestrator,
        page_provider,
        price_provider,
        identity_resolver,
    )


def test_default_disabled_makes_zero_provider_calls() -> None:
    family, geometry, decision, orchestrator, page, price, identity = _context(
        enabled=False
    )
    with pytest.raises(RecipeFirstScannerError):
        asyncio.run(orchestrator.run_once(
            decision=decision, family=family, geometry=geometry
        ))
    assert page.calls == []
    assert price.batch_calls == []
    assert identity.calls == []


def test_valid_a6_b4_calls_only_active_goods_and_builds_exact_recipe() -> None:
    family, geometry, decision, orchestrator, page, _price, _identity = _context()
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert [goods for goods, _name in page.calls] == ["goods-A", "goods-B"]
    selected = result.evaluations[0].selection.selection.recipe.input_items
    assert Counter(item.collection_name for item in selected) == {"A": 6, "B": 4}
    assert result.counters.fallback_family_calls == 0


def test_plan_identity_mismatch_fails_before_page_provider() -> None:
    family, geometry, decision, orchestrator, page, price, identity = _context()
    identity.mapping["goods-A"] = "Wrong exact name"
    with pytest.raises(RecipeFirstScannerError):
        asyncio.run(orchestrator.run_once(
            decision=decision, family=family, geometry=geometry
        ))
    assert page.calls == []
    assert price.batch_calls == []


def test_page_failure_never_calls_fallback_family() -> None:
    family, geometry, decision, orchestrator, page, _price, _identity = _context(
        page_failure="goods-A"
    )
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert result.counters.plan_goods_failed == 1
    assert result.counters.family_selections == 0
    assert result.counters.fallback_family_calls == 0
    assert all(goods != "f" * 24 for goods, _name in page.calls)


def test_insufficient_listings_causes_no_final_valuation() -> None:
    family, geometry, decision, orchestrator, _page, price, _identity = _context()
    orchestrator.listing_provider.pages["goods-B"] = orchestrator.listing_provider.pages[
        "goods-B"
    ][:3]
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert result.evaluations == ()
    assert price.batch_calls == []


def test_successful_recipe_reaches_metrics_risk_and_opportunity() -> None:
    family, geometry, decision, orchestrator, _page, price, _identity = _context()
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert len(price.batch_calls) == 1
    assert len(result.evaluations) == 1
    evaluation = result.evaluations[0]
    assert evaluation.valuation_completed is True
    assert evaluation.metrics is not None
    assert evaluation.risk_decision is not None
    assert evaluation.risk_decision.passed is True
    assert len(result.opportunities) == 1


def test_missing_final_price_skips_metrics_risk_and_opportunity() -> None:
    family, geometry, decision, orchestrator, _page, _price, _identity = _context(
        missing_output_price=True
    )
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    evaluation = result.evaluations[0]
    assert evaluation.valuation_completed is False
    assert evaluation.metrics is None
    assert evaluation.risk_decision is None
    assert result.opportunities == ()


def test_atomic_new_live_cap_blocks_without_partial_provider_call() -> None:
    family, geometry, decision, orchestrator, _page, price, _identity = _context(
        valuation_cap=1
    )
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert price.batch_calls == []
    assert result.counters.live_atomically_blocked == 2
    assert result.evaluations[0].rejection_reason == "VALUATION_REQUEST_CAP_EXCEEDED"


def test_two_selections_reuse_shared_output_names_within_one_session() -> None:
    family, geometry, decision, orchestrator, _page, price, _identity = _context(
        two_selections=True
    )
    result = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert len(result.evaluations) == 2
    assert len(price.batch_calls) == 1
    assert result.counters.run_reuse_hits == len(geometry.outcomes)


def test_normal_souvenir_mix_and_stattrak_paths() -> None:
    family, geometry, decision, orchestrator, _page, _price, _identity = _context(
        souvenir_mix=True
    )
    normal = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert {
        item.souvenir
        for item in normal.evaluations[0].selection.selection.recipe.input_items
    } == {False, True}
    assert all(
        not name.startswith("Souvenir ")
        for name in normal.evaluations[0].output_market_hash_names_requested
    )

    (
        family,
        geometry,
        decision,
        orchestrator,
        _page,
        _price,
        _identity,
    ) = _context(stattrak=True)
    stattrak = asyncio.run(orchestrator.run_once(
        decision=decision, family=family, geometry=geometry
    ))
    assert all(
        name.startswith("StatTrak™ ")
        for name in stattrak.evaluations[0].output_market_hash_names_requested
    )


def test_source_order_permutation_is_deterministic() -> None:
    first = _context(two_selections=True)
    second = _context(two_selections=True)
    for goods_id, values in second[4].pages.items():
        second[4].pages[goods_id] = tuple(reversed(values))
    first_result = asyncio.run(first[3].run_once(
        decision=first[2], family=first[0], geometry=first[1]
    ))
    second_result = asyncio.run(second[3].run_once(
        decision=second[2], family=second[0], geometry=second[1]
    ))
    assert tuple(
        evaluation.selection.selection.selected_listing_ids
        for evaluation in first_result.evaluations
    ) == tuple(
        evaluation.selection.selection.selected_listing_ids
        for evaluation in second_result.evaluations
    )
