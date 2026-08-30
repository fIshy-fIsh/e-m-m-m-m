from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from app.services.buff_item_identity import BuffItemIdentity
from app.services.buff_listing_provider import BuffListing
from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceQuote,
)
from app.services.recipe_solver import (
    RecipeEnumerationConfig,
    RecipeSolverConfig,
)
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_orchestrator import (
    LiveRecipeEvaluation,
    LiveScannerOrchestrator,
    ScannerRunResult,
)
from app.services.scanner_recipe_composition import (
    construct_scanner_recipe_selections,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    enrich_candidates,
)
from app.services.valuation_service import ValuationConfig, ValuationService

PRIMARY_COLLECTION = "Synthetic Phase 13T Collection"
PRIMARY_INPUT_RARITY = "Restricted"
PRIMARY_OUTPUT_RARITY = "Classified"
PRIMARY_GOODS_IDS = tuple(f"scale-goods-{index:02d}" for index in range(10))
PRIMARY_INPUT_NAMES = tuple(
    (
        f"Synthetic Input {index:02d} (Field-Tested)"
        if index < 5
        else f"Souvenir Synthetic Input {index:02d} (Field-Tested)"
    )
    for index in range(10)
)
PRIMARY_OUTPUT_NAMES = tuple(
    f"Synthetic Output {index:02d} (Factory New)" for index in range(10)
)
PRIMARY_LISTING_COUNT = 100
PRIMARY_THEORETICAL_RADIUS_ONE_STATES = 1 + 10 * (
    PRIMARY_LISTING_COUNT - 10
)
DEFAULT_ENUMERATION_CONFIG = RecipeEnumerationConfig(
    max_recipe_candidates_returned=2,
    max_candidate_states_explored=256,
)
PRODUCTION_RISK_CONFIG = RiskFilterConfig(
    min_roi=Decimal("0.05"),
    min_expected_profit_cny=Decimal("20"),
    max_worst_case_loss_pct=Decimal("0.25"),
    min_profit_probability=0.35,
    max_input_total_cost_cny=Decimal("1000"),
)
SOLVER_CONFIG = RecipeSolverConfig(
    input_rarity=PRIMARY_INPUT_RARITY,
    input_count=10,
    sell_fee_rate=Decimal("0.025"),
)


@dataclass(frozen=True, kw_only=True)
class OfflineScannerFixture:
    goods_ids: tuple[str, ...]
    listings_by_goods: dict[str, tuple[BuffListing, ...]]
    names_by_goods: dict[str, str]
    metadata: PinnedSkinMetadataResolver
    output_names: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class OfflineRun:
    result: ScannerRunResult
    listing_provider: OfflineListingProvider
    price_provider: RecordingPriceProvider


class OfflineListingProvider:
    def __init__(
        self,
        listings_by_goods: dict[str, tuple[BuffListing, ...]],
    ) -> None:
        self._listings_by_goods = listings_by_goods
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        return list(self._listings_by_goods.get(goods_id, ()))


class OfflineIdentityResolver:
    def __init__(self, names_by_goods: dict[str, str]) -> None:
        self._names_by_goods = names_by_goods
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
        self.calls.append(goods_id)
        name = self._names_by_goods.get(goods_id)
        if name is None:
            return None
        return BuffItemIdentity(market_hash_name=name, goods_id=goods_id)


class RecordingPriceProvider(MockPriceProvider):
    def __init__(self, output_names: tuple[str, ...]) -> None:
        super().__init__(
            {
                name: PriceQuote(
                    market_hash_name=name,
                    price_cny=Decimal("25"),
                    source="offline-phase-13t-4a",
                )
                for name in output_names
            }
        )
        self.calls: list[tuple[str, ...]] = []

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        self.calls.append(tuple(market_hash_names))
        return await super().get_prices(market_hash_names)


def _metadata_row(
    name: str,
    rarity: str,
    *,
    stattrak: bool = False,
    souvenir: bool = False,
    collection: str = PRIMARY_COLLECTION,
) -> dict[str, object]:
    return {
        "market_hash_name": name,
        "collection_name": collection,
        "rarity": rarity,
        "min_float": 0.0,
        "max_float": 1.0,
        "name": name,
        "weapon": "Synthetic Weapon",
        "category": "Rifle",
        "stattrak": stattrak,
        "souvenir": souvenir,
        "paint_index": 1,
    }


def _primary_fixture() -> OfflineScannerFixture:
    names_by_goods = dict(zip(PRIMARY_GOODS_IDS, PRIMARY_INPUT_NAMES, strict=True))
    listings_by_goods: dict[str, tuple[BuffListing, ...]] = {}
    for goods_index, goods_id in enumerate(PRIMARY_GOODS_IDS):
        listings: list[BuffListing] = []
        for depth in range(10):
            rank = depth * len(PRIMARY_GOODS_IDS) + goods_index
            listings.append(
                BuffListing(
                    listing_id=f"scale-listing-{rank:03d}",
                    goods_id=goods_id,
                    market_hash_name=None,
                    price_cny=(
                        Decimal("10") + Decimal(rank) / Decimal("1000")
                    ),
                    paintwear=(
                        Decimal("0.10") + Decimal(rank) / Decimal("10000")
                    ),
                    asset_id=f"scale-asset-{rank:03d}",
                    paintseed=rank,
                    source="buff",
                )
            )
        listings_by_goods[goods_id] = tuple(listings)

    input_rows = [
        _metadata_row(
            name,
            PRIMARY_INPUT_RARITY,
            souvenir=name.startswith("Souvenir "),
        )
        for name in PRIMARY_INPUT_NAMES
    ]
    output_rows = [
        _metadata_row(name, PRIMARY_OUTPUT_RARITY)
        for name in PRIMARY_OUTPUT_NAMES
    ]
    return OfflineScannerFixture(
        goods_ids=PRIMARY_GOODS_IDS,
        listings_by_goods=listings_by_goods,
        names_by_goods=names_by_goods,
        metadata=PinnedSkinMetadataResolver.from_payload(
            {"items": [*input_rows, *output_rows]}
        ),
        output_names=PRIMARY_OUTPUT_NAMES,
    )


def _two_bucket_fixture() -> OfflineScannerFixture:
    normal_goods = "two-bucket-normal"
    stattrak_goods = "two-bucket-stattrak"
    normal_input = "Synthetic Two-Bucket Input (Field-Tested)"
    stattrak_input = "StatTrak™ Synthetic Two-Bucket Input (Field-Tested)"
    normal_output = "Synthetic Two-Bucket Output (Factory New)"
    stattrak_output = "StatTrak™ Synthetic Two-Bucket Output (Factory New)"
    listings_by_goods: dict[str, tuple[BuffListing, ...]] = {}
    for mode_index, goods_id in enumerate((normal_goods, stattrak_goods)):
        listings_by_goods[goods_id] = tuple(
            BuffListing(
                listing_id=f"two-bucket-{mode_index}-{index:02d}",
                goods_id=goods_id,
                market_hash_name=None,
                price_cny=Decimal("10") + Decimal(index) / Decimal("100"),
                paintwear=Decimal("0.10") + Decimal(index) / Decimal("10000"),
                asset_id=f"two-bucket-asset-{mode_index}-{index:02d}",
                paintseed=mode_index * 100 + index,
                source="buff",
            )
            for index in range(10)
        )
    return OfflineScannerFixture(
        goods_ids=(normal_goods, stattrak_goods),
        listings_by_goods=listings_by_goods,
        names_by_goods={
            normal_goods: normal_input,
            stattrak_goods: stattrak_input,
        },
        metadata=PinnedSkinMetadataResolver.from_payload(
            {
                "items": [
                    _metadata_row(normal_input, PRIMARY_INPUT_RARITY),
                    _metadata_row(
                        stattrak_input,
                        PRIMARY_INPUT_RARITY,
                        stattrak=True,
                    ),
                    _metadata_row(normal_output, PRIMARY_OUTPUT_RARITY),
                    _metadata_row(
                        stattrak_output,
                        PRIMARY_OUTPUT_RARITY,
                        stattrak=True,
                    ),
                ]
            }
        ),
        output_names=(normal_output, stattrak_output),
    )


def _run_fixture(
    fixture: OfflineScannerFixture,
    *,
    max_valuation_requests: int,
    enumeration_config: RecipeEnumerationConfig = DEFAULT_ENUMERATION_CONFIG,
) -> OfflineRun:
    listing_provider = OfflineListingProvider(fixture.listings_by_goods)
    price_provider = RecordingPriceProvider(fixture.output_names)
    orchestrator = LiveScannerOrchestrator(
        listing_provider=listing_provider,
        identity_resolver=OfflineIdentityResolver(fixture.names_by_goods),
        metadata_resolver=fixture.metadata,
        valuation_service=ValuationService(price_provider, ValuationConfig()),
        max_valuation_requests_per_run=max_valuation_requests,
        solver_config=SOLVER_CONFIG,
        risk_config=PRODUCTION_RISK_CONFIG,
        enumeration_config=enumeration_config,
    )
    return OfflineRun(
        result=asyncio.run(orchestrator.run_once(fixture.goods_ids)),
        listing_provider=listing_provider,
        price_provider=price_provider,
    )


async def _enrich_fixture(
    fixture: OfflineScannerFixture,
) -> tuple[TradeUpEnrichedInput, ...]:
    enricher = InMemoryTradeUpInputEnricher(fixture.metadata)
    enriched: list[TradeUpEnrichedInput] = []
    for goods_id in fixture.goods_ids:
        name = fixture.names_by_goods[goods_id]
        stattrak = name.startswith("StatTrak™ ")
        souvenir = name.startswith("Souvenir ")
        candidates = [
            TradeUpInputCandidate(
                listing_id=listing.listing_id,
                goods_id=listing.goods_id,
                market_hash_name=name,
                price_cny=listing.price_cny,
                paintwear=listing.paintwear,
                asset_id=listing.asset_id,
                source=listing.source,
                stattrak=stattrak,
                souvenir=souvenir,
            )
            for listing in fixture.listings_by_goods[goods_id]
        ]
        result = enrich_candidates(candidates, enricher)
        assert result.rejected == ()
        enriched.extend(result.enriched)
    return tuple(enriched)


def _first_seen_output_names(
    evaluation: LiveRecipeEvaluation,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            result.output_market_hash_name
            for result in evaluation.recipe.recipe.tradeup_results
        )
    )


def _selection_identities(result: ScannerRunResult) -> tuple[tuple[str, ...], ...]:
    return tuple(
        evaluation.recipe.selected_listing_ids
        for evaluation in result.recipe_evaluations
    )


def _offer_keys(
    evaluation: LiveRecipeEvaluation,
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (listing.source, listing.goods_id, listing.listing_id)
        for listing in evaluation.listings
    )


def _expected_primary_offer_key(rank: int) -> tuple[str, str, str]:
    goods_id = PRIMARY_GOODS_IDS[rank % len(PRIMARY_GOODS_IDS)]
    return ("buff", goods_id, f"scale-listing-{rank:03d}")


def _assert_primary_structure(run: OfflineRun) -> None:
    result = run.result
    diagnostics = result.diagnostics.recipe_composition
    assert diagnostics is not None
    assert result.goods_ids == PRIMARY_GOODS_IDS
    assert run.listing_provider.calls == list(PRIMARY_GOODS_IDS)
    assert result.counters.goods_ids_requested == 10
    assert result.counters.goods_ids_succeeded == 10
    assert result.counters.listings_received == PRIMARY_LISTING_COUNT
    assert result.counters.candidate_accepted == PRIMARY_LISTING_COUNT
    assert result.counters.candidate_rejected == 0
    assert result.counters.metadata_resolved == PRIMARY_LISTING_COUNT
    assert result.counters.metadata_unresolved == 0
    assert result.counters.input_items_created == PRIMARY_LISTING_COUNT
    assert diagnostics.aggregate_candidate_limit == 2
    assert diagnostics.aggregate_state_limit == 256
    assert diagnostics.active_bucket_count == 1
    assert diagnostics.participating_bucket_count == 1
    assert diagnostics.returned_candidates == 2
    assert diagnostics.states_explored == 2
    assert diagnostics.returned_candidates <= 2
    assert diagnostics.states_explored <= 256
    assert result.counters.recipes_evaluated == diagnostics.returned_candidates
    assert len(result.recipe_evaluations) == diagnostics.returned_candidates

    baseline, alternative = result.recipe_evaluations
    expected_baseline = tuple(_expected_primary_offer_key(rank) for rank in range(10))
    expected_alternative = tuple(
        [*(_expected_primary_offer_key(rank) for rank in range(9)),
         _expected_primary_offer_key(10)]
    )
    assert _offer_keys(baseline) == expected_baseline
    assert _offer_keys(alternative) == expected_alternative
    assert len(set(_offer_keys(baseline))) == 10
    assert len(set(_offer_keys(alternative))) == 10
    assert len(set(_offer_keys(baseline)) & set(_offer_keys(alternative))) == 9
    assert len(set(_offer_keys(baseline)) ^ set(_offer_keys(alternative))) == 2

    for evaluation in result.recipe_evaluations:
        assert len(evaluation.recipe.recipe.input_items) == 10
        assert len(evaluation.listings) == 10
        assert any(item.souvenir for item in evaluation.recipe.recipe.input_items)
        assert any(listing.souvenir for listing in evaluation.listings)
        for item, listing in zip(
            evaluation.recipe.recipe.input_items,
            evaluation.listings,
            strict=True,
        ):
            assert item.market_hash_name == listing.market_hash_name
            assert item.price_cny == listing.price_cny
            assert item.actual_float == float(listing.paintwear)
            assert item.collection_name == PRIMARY_COLLECTION
            assert item.rarity == PRIMARY_INPUT_RARITY
            assert item.stattrak is listing.stattrak
            assert item.souvenir is listing.souvenir


def test_primary_deep_pool_real_path_is_bounded_rehydrated_and_deterministic() -> None:
    fixture = _primary_fixture()
    first = _run_fixture(fixture, max_valuation_requests=60)
    second = _run_fixture(fixture, max_valuation_requests=60)

    _assert_primary_structure(first)
    _assert_primary_structure(second)
    assert PRIMARY_LISTING_COUNT >= 90
    assert PRIMARY_THEORETICAL_RADIUS_ONE_STATES == 901

    first_names = tuple(
        _first_seen_output_names(evaluation)
        for evaluation in first.result.recipe_evaluations
    )
    expected_logical_requests = sum(len(names) for names in first_names)
    cross_recipe_repeats = len(set(first_names[0]) & set(first_names[1]))
    assert tuple(len(names) for names in first_names) == (10, 10)
    assert cross_recipe_repeats == 10
    # Phase 14B: Recipe 0 issues ONE provider call with all 10 NEW LIVE
    # names; Recipe 1 reuses those 10 names via the run memo (no second
    # provider call). Legacy counter semantics for `attempted` are
    # preserved: BOTH recipes are admitted and contribute their full
    # `requested_count` to `valuation_requests_attempted`.
    assert first.price_provider.calls == [first_names[0]]
    assert expected_logical_requests == 20
    assert sum(len(call) for call in first.price_provider.calls) == 10
    assert first.result.counters.valuation_requests_attempted == 20
    assert first.result.counters.valuation_requests_succeeded == 20
    assert first.result.counters.valuation_requests_failed == 0
    assert first.result.counters.valuation_requests_blocked == 0
    assert first.result.counters.recipes_fully_valued == 2
    assert first.result.counters.live_demand == 10
    assert first.result.counters.live_attempted == 10
    assert first.result.counters.live_succeeded == 10
    assert first.result.counters.live_failed == 0
    assert first.result.counters.live_atomically_blocked == 0
    assert first.result.counters.run_reuse_hits == 10
    assert first.result.counters.run_reuse_successes == 10
    assert first.result.counters.run_reuse_failures == 0
    assert first.result.counters.cache_hits_fresh_selected == 0
    assert first.result.counters.cache_misses == 0
    assert first.result.counters.cache_policy_blocked == 0
    assert first.result.counters.cache_expired == 0
    assert first.result.counters.cache_selection_failures == 0
    assert all(
        evaluation.metrics is not None
        and evaluation.risk_decision is not None
        for evaluation in first.result.recipe_evaluations
    )
    assert first.result.counters.opportunities_found == 0

    assert _selection_identities(first.result) == _selection_identities(second.result)
    assert (
        first.result.diagnostics.recipe_composition
        == second.result.diagnostics.recipe_composition
    )
    # Cross-run memo is NOT allowed: each separate run has its own
    # 10 NEW LIVE demand and its own single provider call.
    assert first.price_provider.calls == second.price_provider.calls
    assert first.result.counters == second.result.counters


def test_exact_and_one_below_valuation_caps_are_atomic_and_search_independent() -> None:
    fixture = _primary_fixture()
    discovery = _run_fixture(fixture, max_valuation_requests=60)
    request_names = tuple(
        _first_seen_output_names(evaluation)
        for evaluation in discovery.result.recipe_evaluations
    )
    total_required = sum(len(names) for names in request_names)
    assert tuple(len(names) for names in request_names) == (10, 10)
    assert total_required == 20

    # Phase 14B: each recipe's NEW LIVE demand = first-seen unique names
    # not yet memoized. Because both recipes demand the SAME 10 names,
    # Recipe 1 reuses all 10 via the run memo (NEW LIVE demand = 0).
    # Therefore the "exact boundary" cap for the combined demand is
    # `first_required = 10` (Recipe 0's NEW LIVE). "One below" is 9.
    first_required = len(request_names[0])
    blocked_required = total_required

    exact = _run_fixture(fixture, max_valuation_requests=first_required)
    one_below = _run_fixture(
        fixture,
        max_valuation_requests=first_required - 1,
    )
    _assert_primary_structure(exact)
    _assert_primary_structure(one_below)

    # Exact boundary: Recipe 0 admitted (10 NEW LIVE); Recipe 1 admitted
    # (0 NEW LIVE because all 10 are memoed). One provider call with the
    # 10 NEW LIVE names. Legacy `attempted` is the sum of ADMITTED
    # recipe `requested_count`s = 20 (preserved from Phase 13T).
    assert exact.price_provider.calls == [request_names[0]]
    assert sum(len(call) for call in exact.price_provider.calls) == first_required
    assert exact.result.counters.valuation_requests_attempted == total_required
    assert exact.result.counters.valuation_requests_blocked == 0
    assert exact.result.counters.recipes_fully_valued == 2
    assert exact.result.counters.recipes_valuation_failed == 0
    assert exact.result.counters.live_demand == first_required
    assert exact.result.counters.live_attempted == first_required
    assert exact.result.counters.live_succeeded == first_required
    assert exact.result.counters.live_atomically_blocked == 0
    assert exact.result.counters.run_reuse_hits == first_required
    assert exact.result.counters.run_reuse_successes == first_required
    assert all(
        evaluation.valuation_completed
        and evaluation.valuation_prices_resolved
        == len(evaluation.output_market_hash_names_requested)
        for evaluation in exact.result.recipe_evaluations
    )

    # One-below boundary: Recipe 0 blocked (10 NEW LIVE > 9 cap); Recipe 1
    # prepare sees Recipe 0's blocked names as NEW LIVE again (not
    # memoed) and is ALSO blocked (10 NEW LIVE > 9). ZERO provider
    # calls. Legacy `attempted` = 0 (no ADMITTED recipe); legacy
    # `blocked` = 20 (both recipes). `live_demand` = 20; `live_attempted`
    # = 0; `live_atomically_blocked` = 20.
    assert one_below.price_provider.calls == []
    assert sum(len(call) for call in one_below.price_provider.calls) == 0
    assert one_below.result.counters.valuation_requests_attempted == 0
    assert one_below.result.counters.valuation_requests_succeeded == 0
    assert one_below.result.counters.valuation_requests_blocked == blocked_required
    assert one_below.result.counters.recipes_fully_valued == 0
    assert one_below.result.counters.recipes_valuation_failed == 2
    assert one_below.result.counters.live_demand == blocked_required
    assert one_below.result.counters.live_attempted == 0
    assert one_below.result.counters.live_succeeded == 0
    assert one_below.result.counters.live_atomically_blocked == blocked_required
    assert one_below.result.counters.run_reuse_hits == 0
    assert one_below.result.recipe_evaluations[0].valuation_completed is False
    blocked = one_below.result.recipe_evaluations[1]
    assert blocked.valuation_completed is False
    assert blocked.valuation_prices_resolved == 0
    assert blocked.valued_tradeup_results == ()
    assert blocked.metrics is None
    assert blocked.risk_decision is None
    assert blocked.rejection_reason == "VALUATION_REQUEST_CAP_EXCEEDED"

    assert _selection_identities(exact.result) == _selection_identities(
        one_below.result
    )
    assert (
        exact.result.diagnostics.recipe_composition
        == one_below.result.diagnostics.recipe_composition
    )


def test_two_bucket_real_composition_uses_one_aggregate_budget() -> None:
    fixture = _two_bucket_fixture()
    run = _run_fixture(fixture, max_valuation_requests=2)
    diagnostics = run.result.diagnostics.recipe_composition
    assert diagnostics is not None

    assert diagnostics.active_bucket_count == 2
    assert diagnostics.participating_bucket_count == 2
    assert [bucket.stattrak for bucket in diagnostics.buckets] == [False, True]
    assert [bucket.candidate_quota for bucket in diagnostics.buckets] == [1, 1]
    assert [bucket.state_quota for bucket in diagnostics.buckets] == [128, 128]
    assert [bucket.returned_candidates for bucket in diagnostics.buckets] == [1, 1]
    assert [bucket.states_explored for bucket in diagnostics.buckets] == [1, 1]
    assert diagnostics.returned_candidates == 2
    assert diagnostics.states_explored == 2
    assert diagnostics.returned_candidates <= 2
    assert diagnostics.states_explored <= 256
    assert run.result.counters.recipes_evaluated == 2
    assert run.result.counters.recipes_fully_valued == 2
    assert run.result.counters.valuation_requests_attempted == 2
    assert sum(len(call) for call in run.price_provider.calls) == 2
    assert all(
        not item.stattrak
        for item in run.result.recipe_evaluations[0].recipe.recipe.input_items
    )
    assert all(
        item.stattrak
        for item in run.result.recipe_evaluations[1].recipe.recipe.input_items
    )


def test_one_by_one_orchestrator_result_is_legacy_equivalent() -> None:
    fixture = _primary_fixture()
    one_by_one = RecipeEnumerationConfig(
        max_recipe_candidates_returned=1,
        max_candidate_states_explored=1,
    )
    run = _run_fixture(
        fixture,
        max_valuation_requests=10,
        enumeration_config=one_by_one,
    )
    enriched = asyncio.run(_enrich_fixture(fixture))
    legacy = construct_scanner_recipe_selections(
        enriched_inputs=enriched,
        canonical_skins=fixture.metadata.skins,
        solver_config=SOLVER_CONFIG,
    )
    diagnostics = run.result.diagnostics.recipe_composition
    assert diagnostics is not None

    assert len(legacy) == 1
    assert len(run.result.recipe_evaluations) == 1
    assert run.result.recipe_evaluations[0].recipe == legacy[0]
    assert diagnostics.aggregate_candidate_limit == 1
    assert diagnostics.aggregate_state_limit == 1
    assert diagnostics.returned_candidates == 1
    assert diagnostics.states_explored == 1
    assert run.result.counters.recipes_evaluated == 1
    assert run.result.counters.recipes_fully_valued == 1
    assert run.result.counters.valuation_requests_attempted == 10
    assert run.result.recipe_evaluations[0].metrics is not None
    assert run.result.recipe_evaluations[0].risk_decision is not None
