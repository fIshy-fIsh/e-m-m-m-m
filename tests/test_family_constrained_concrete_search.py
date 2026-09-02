"""Phase 16E — Dedicated family-constrained concrete search tests."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest

from app.services.family_constrained_concrete_search import (
    FamilyConstrainedConcreteSearchError,
    search_family_constrained_recipes,
)
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import StatTrakMode, build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem


def _output_rows(
    collections: tuple[str, ...],
    *,
    stattrak: bool = False,
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
                    market_hash_name=(
                        f"{prefix}{collection} Output (" f"{wear})"
                    ),
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
    index: int,
    adjusted: float,
    goods_id: str | None = None,
    stattrak: bool = False,
    souvenir: bool = False,
) -> TradeUpEnrichedInput:
    prefix = "StatTrak™ " if stattrak else ("Souvenir " if souvenir else "")
    name = f"{prefix}{collection} Input {index} (Field-Tested)"
    candidate = TradeUpInputCandidate(
        listing_id=f"listing-{collection}-{index}",
        goods_id=goods_id or f"goods-{collection}-{index}",
        market_hash_name=name,
        price_cny=Decimal(index + 1),
        paintwear=Decimal(str(adjusted)),
        asset_id=f"asset-{collection}-{index}",
        source="buff",
        stattrak=stattrak,
        souvenir=souvenir,
    )
    return TradeUpEnrichedInput(
        candidate=candidate,
        input_item=InputItem(
            market_hash_name=name,
            collection_name=collection,
            rarity="Restricted",
            actual_float=adjusted,
            min_float=0.0,
            max_float=1.0,
            price_cny=candidate.price_cny,
            stattrak=stattrak,
            souvenir=souvenir,
        ),
    )


def _search(
    counts: tuple[tuple[str, int], ...],
    enriched: tuple[TradeUpEnrichedInput, ...],
    *,
    enumeration: RecipeEnumerationConfig | None = None,
    max_per_collection: int | None = None,
    stattrak: bool = False,
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
    return family, search_family_constrained_recipes(
        family,
        geometry=compute_recipe_family_geometry(
            family, finish_index=finish_index
        ),
        finish_index=finish_index,
        enriched_inputs=enriched,
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            max_candidates_per_collection=max_per_collection,
            target_stattrak=stattrak,
        ),
        enumeration_config=enumeration or RecipeEnumerationConfig(),
    )


@pytest.mark.parametrize(
    "counts",
    [
        (("A", 10),),
        (("A", 6), ("B", 4)),
        (("A", 4), ("B", 3), ("C", 3)),
    ],
)
def test_exact_family_counts(counts: tuple[tuple[str, int], ...]) -> None:
    enriched = tuple(
        _enriched(collection=name, index=index, adjusted=index / 100)
        for name, count in counts
        for index in range(count)
    )
    family, result = _search(counts, enriched)
    assert len(result.selections) == 1
    selected = result.selections[0].selection.recipe.input_items
    assert Counter(item.collection_name for item in selected) == dict(
        family.collection_counts
    )


def test_unrelated_collection_never_selected() -> None:
    enriched = (
        *tuple(_enriched(collection="A", index=i, adjusted=i / 100) for i in range(10)),
        *tuple(_enriched(collection="Z", index=i, adjusted=0.0) for i in range(10)),
    )
    _family, result = _search((("A", 10),), enriched)
    assert all(
        item.collection_name == "A"
        for selection in result.selections
        for item in selection.selection.recipe.input_items
    )


def test_insufficient_required_collection_returns_no_selection() -> None:
    enriched = (
        *tuple(_enriched(collection="A", index=i, adjusted=i / 100) for i in range(6)),
        *tuple(_enriched(collection="B", index=i, adjusted=i / 100) for i in range(3)),
    )
    _family, result = _search((("A", 6), ("B", 4)), enriched)
    assert result.selections == ()
    assert result.diagnostics.states_explored == 0


def test_same_goods_id_multiple_unique_listings_allowed() -> None:
    enriched = tuple(
        _enriched(collection="A", index=i, adjusted=i / 100, goods_id="same")
        for i in range(10)
    )
    _family, result = _search((("A", 10),), enriched)
    assert len(result.selections) == 1
    assert len(set(result.selections[0].selection.selected_listing_ids)) == 10


def test_duplicate_listing_provenance_fails_closed() -> None:
    item = _enriched(collection="A", index=0, adjusted=0.0)
    with pytest.raises(FamilyConstrainedConcreteSearchError):
        _search((("A", 10),), (item, item, *tuple(
            _enriched(collection="A", index=i, adjusted=i / 100)
            for i in range(1, 9)
        )))


def test_source_order_permutation_is_deterministic() -> None:
    enriched = tuple(
        _enriched(collection="A", index=i, adjusted=(20 - i) / 100)
        for i in range(20)
    )
    _family, first = _search((("A", 10),), enriched)
    _family, second = _search((("A", 10),), tuple(reversed(enriched)))
    assert tuple(
        selection.selection.selected_listing_ids for selection in first.selections
    ) == tuple(
        selection.selection.selected_listing_ids for selection in second.selections
    )


def test_radius_one_alternative_preserves_family_counts() -> None:
    enriched = (
        *tuple(_enriched(collection="A", index=i, adjusted=i / 100) for i in range(8)),
        *tuple(_enriched(collection="B", index=i, adjusted=i / 100) for i in range(6)),
    )
    family, result = _search((("A", 6), ("B", 4)), enriched)
    assert result.diagnostics.theoretical_radius_one_states == 21
    assert result.diagnostics.states_explored == 2
    assert len(result.selections) == 2
    for selection in result.selections:
        assert Counter(
            item.collection_name for item in selection.selection.recipe.input_items
        ) == dict(family.collection_counts)


def test_default_2_256_bounds_and_explicit_state_bound() -> None:
    enriched = tuple(
        _enriched(collection="A", index=i, adjusted=i / 1000)
        for i in range(50)
    )
    _family, default = _search((("A", 10),), enriched)
    assert len(default.selections) == 2
    assert default.diagnostics.states_explored == 2
    _family, bounded = _search(
        (("A", 10),),
        enriched,
        enumeration=RecipeEnumerationConfig(
            max_recipe_candidates_returned=2,
            max_candidate_states_explored=2,
        ),
    )
    assert bounded.diagnostics.states_explored == 2
    assert bounded.diagnostics.exploration_limit_reached is False


def test_max_candidates_per_collection_honored() -> None:
    enriched = tuple(
        _enriched(collection="A", index=i, adjusted=i / 100)
        for i in range(20)
    )
    _family, result = _search(
        (("A", 10),), enriched, max_per_collection=10
    )
    assert result.diagnostics.retained_input_count == 10
    assert result.diagnostics.theoretical_radius_one_states == 1


def test_memory_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.family_constrained_concrete_search as module

    enriched = tuple(
        _enriched(collection="A", index=i, adjusted=i / 100)
        for i in range(10)
    )

    def boom(*_args: object, **_kwargs: object) -> object:
        raise MemoryError("must propagate")

    monkeypatch.setattr(module, "calculate_adjusted_float", boom)
    with pytest.raises(MemoryError):
        _search((("A", 10),), enriched)
