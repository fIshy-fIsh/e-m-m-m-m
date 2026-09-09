"""Phase 17C-R1 collection-scoped discovery-budget regressions.

All tests are pure/offline. No market provider method is allowed to run.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from itertools import islice
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_family import (
    RecipeFamilyGenerator,
    RecipeFamilyIdentityError,
)
from app.services.recipe_first_runtime_contract import (
    RecipeFirstDiscoveryBudget,
    RecipeFirstOutputFormat,
    RecipeFirstRuntimeConfig,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
    RecipeFirstRuntimeCoordinatorError,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.valuation_service import ValuationConfig, ValuationService

ROOT = Path(__file__).resolve().parent.parent
IDENTITY_PATH = ROOT / "data" / "identity" / "buff_identity_v1.json"
METADATA_PATH = ROOT / "data" / "metadata" / "skin_metadata_v1.json"
PHOENIX_COLLECTION = "The Phoenix Collection"
PHOENIX_KEY = "45bfd0f0d3e7405588acdcf7"
PHOENIX_HASH = (
    "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
)
GLOBAL_FIRST_COLLECTION = "Limited Edition Item"
GLOBAL_FIRST_KEY = "40a60d49838d4fe7a70126ec"
GLOBAL_FIRST_HASH = (
    "40a60d49838d4fe7a70126ec4bf5e5bb29cea5d9ea00cc6327c49066e343288f"
)


class _NoMarketBatch:
    async def get_price_batch_with_selection(self, *args, **kwargs):
        raise AssertionError("SteamDT seam must not run in structural proof")


class _NoMarketListing:
    async def get_listings(self, goods_id: str):
        raise AssertionError("BUFF seam must not run in structural proof")


class _NoMarketPrice:
    async def get_price(self, market_hash_name: str) -> PriceQuote:
        raise AssertionError("final market seam must not run")

    async def get_prices(self, names: list[str]) -> PriceLookupResult:
        raise AssertionError("final market seam must not run")


def _authorities():
    identity = BuffCommunityIdentityResolver.from_snapshot_path(IDENTITY_PATH)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    return identity, metadata, finish_index


def _generator(*, allowlist: tuple[str, ...]):
    identity, metadata, finish_index = _authorities()
    unrestricted = RecipeFamilyGenerator.from_catalogs(
        skins=metadata.skins,
        identity_resolver=identity,
        finish_index=finish_index,
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
    )
    return unrestricted, unrestricted.with_collection_allowlist(allowlist)


def _coordinator(*, allowlist: tuple[str, ...], state_cap: int):
    identity, metadata, finish_index = _authorities()
    return RecipeFirstRuntimeCoordinator(
        config=RecipeFirstRuntimeConfig(
            enabled=True,
            preview=False,
            input_rarities=("Classified",),
            stattrak_modes=(StatTrakMode.NORMAL,),
            collection_allowlist=allowlist,
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
            max_family_states_considered=state_cap,
            max_prescreen_names=100,
            max_prescreen_batch_dispatches=10,
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=_NoMarketBatch(),
        listing_provider=_NoMarketListing(),
        valuation_service=ValuationService(
            _NoMarketPrice(),
            ValuationConfig(require_all_prices=True),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("0"),
            min_expected_profit_cny=Decimal("0"),
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("1"),
        ),
    )


def test_phoenix_one_state_is_first_and_only_visited_in_scope() -> None:
    coordinator = _coordinator(
        allowlist=(PHOENIX_COLLECTION,),
        state_cap=1,
    )
    phases = []
    candidates, summary = coordinator._discover(phases=phases)

    assert summary.visited == 1
    assert summary.infeasible == 0
    assert summary.contract_failed == 0
    assert len(candidates) == 1
    family = candidates[0].family
    assert family.collection_counts == ((PHOENIX_COLLECTION, 10),)
    assert family.family_key == PHOENIX_KEY
    assert family.family_hash == PHOENIX_HASH


def test_empty_allowlist_preserves_unrestricted_first_family_and_identity() -> None:
    unrestricted, same = _generator(allowlist=())
    assert same is unrestricted
    assert unrestricted.stratum.eligible_collections[0] == GLOBAL_FIRST_COLLECTION
    first = next(unrestricted.iter_families())
    assert first.collection_counts == ((GLOBAL_FIRST_COLLECTION, 10),)
    assert first.family_key == GLOBAL_FIRST_KEY
    assert first.family_hash == GLOBAL_FIRST_HASH


def test_multi_collection_allowlist_constrains_before_iteration() -> None:
    allowlist = (PHOENIX_COLLECTION, "The Chroma Collection")
    unrestricted, constrained = _generator(allowlist=allowlist)
    expected = tuple(
        name
        for name in unrestricted.stratum.eligible_collections
        if name in set(allowlist)
    )
    assert constrained.stratum.eligible_collections == expected
    assert expected == tuple(sorted(expected))

    first_five = tuple(islice(constrained.iter_families(), 5))
    assert len(first_five) == 5
    assert all(
        {name for name, _count in family.collection_counts}.issubset(allowlist)
        for family in first_five
    )
    assert first_five == tuple(
        islice(constrained.iter_families(), 5)
    )


def test_multi_collection_state_cap_counts_only_in_scope_states() -> None:
    allowlist = (PHOENIX_COLLECTION, "The Chroma Collection")
    coordinator = _coordinator(allowlist=allowlist, state_cap=3)
    candidates, summary = coordinator._discover(phases=[])

    assert summary.visited == 3
    assert all(
        {name for name, _count in item.family.collection_counts}.issubset(
            allowlist
        )
        for item in candidates
    )


def test_unknown_allowlist_collection_remains_fail_closed() -> None:
    with pytest.raises(RecipeFirstRuntimeCoordinatorError, match="collection"):
        _coordinator(
            allowlist=("Not A Pinned Collection",),
            state_cap=1,
        )


def test_allowlist_is_exact_case_sensitive_and_never_trimmed() -> None:
    _unrestricted, lower = _generator(
        allowlist=("the phoenix collection",)
    )
    assert lower.stratum.eligible_collections == ()
    assert tuple(lower.iter_families()) == ()

    with pytest.raises(RecipeFamilyIdentityError, match="exact tuple"):
        _generator(allowlist=(f" {PHOENIX_COLLECTION}",))


def test_constraining_generator_does_not_iterate_family_states() -> None:
    unrestricted, constrained = _generator(
        allowlist=(PHOENIX_COLLECTION,)
    )
    # Constraining builds only a new immutable stratum. Family state
    # iteration remains lazy until the caller explicitly asks for it.
    iterator = constrained.iter_families()
    assert isinstance(iterator, Iterator)
    assert unrestricted.count() > constrained.count()
    first = next(iterator)
    assert first.family_key == PHOENIX_KEY


def test_validation_bound_remains_exactly_one() -> None:
    coordinator = _coordinator(
        allowlist=(PHOENIX_COLLECTION,),
        state_cap=1,
    )
    assert coordinator.discovery_budget.max_family_states_considered == 1
    candidates, summary = coordinator._discover(phases=[])
    assert summary.visited == 1
    assert candidates[0].family.family_hash == PHOENIX_HASH
