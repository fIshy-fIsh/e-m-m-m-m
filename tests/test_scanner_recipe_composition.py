from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.scanner_recipe_composition as composition_module
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import build_output_candidates_by_collection
from app.services.recipe_solver import RecipeSolverConfig
from app.services.scanner_recipe_composition import (
    ScannerRecipeCompositionError,
    construct_scanner_recipe_selections,
    is_current_standard_trade_up_output_eligible,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem

METADATA_PATH = Path("data/metadata/skin_metadata_v1.json")
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "scanner_recipe_composition.py"
)
COBBLESTONE = "The Cobblestone Collection"
NORMAL_INPUT = "CZ75-Auto | Chalice (Factory New)"
SOUVENIR_INPUT = "Souvenir CZ75-Auto | Chalice (Factory New)"
NORMAL_KNIGHT_FN = "M4A1-S | Knight (Factory New)"
NORMAL_KNIGHT_MW = "M4A1-S | Knight (Minimal Wear)"
SOUVENIR_KNIGHT_FN = "Souvenir M4A1-S | Knight (Factory New)"
SOUVENIR_KNIGHT_MW = "Souvenir M4A1-S | Knight (Minimal Wear)"


def _skin(
    name: str,
    *,
    rarity: str,
    stattrak: bool = False,
    souvenir: bool = False,
    collection: str = COBBLESTONE,
) -> SkinMetadata:
    return SkinMetadata(
        market_hash_name=name,
        name=name,
        weapon="Synthetic Weapon",
        rarity=rarity,
        category="Rifle",
        collection_name=collection,
        min_float=0.0,
        max_float=0.1,
        stattrak=stattrak,
        souvenir=souvenir,
        raw={"canonical": True},
    )


def _enriched(
    index: int,
    skin: SkinMetadata,
    *,
    goods_id: str | None = None,
) -> TradeUpEnrichedInput:
    paintwear = Decimal("0.01") + Decimal(index) / Decimal("10000")
    candidate = TradeUpInputCandidate(
        listing_id=f"listing-{index}",
        goods_id=goods_id or f"goods-{index}",
        market_hash_name=skin.market_hash_name,
        price_cny=Decimal("10") + Decimal(index) / Decimal("100"),
        paintwear=paintwear,
        asset_id=f"asset-{index}",
        stattrak=skin.stattrak,
        souvenir=skin.souvenir,
    )
    return TradeUpEnrichedInput(
        candidate=candidate,
        input_item=InputItem(
            market_hash_name=skin.market_hash_name,
            collection_name=skin.collection_name or COBBLESTONE,
            rarity=skin.rarity,
            actual_float=float(paintwear),
            min_float=skin.min_float,
            max_float=skin.max_float,
            price_cny=candidate.price_cny,
            stattrak=skin.stattrak,
            souvenir=skin.souvenir,
        ),
    )


def _config(
    *,
    target_stattrak: bool | None = None,
    target_souvenir: bool | None = None,
) -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity="Restricted",
        input_count=10,
        sell_fee_rate=Decimal("0"),
        target_stattrak=target_stattrak,
        target_souvenir=target_souvenir,
    )


def _catalog() -> tuple[SkinMetadata, ...]:
    normal_input = _skin(NORMAL_INPUT, rarity="Restricted")
    souvenir_input = _skin(
        SOUVENIR_INPUT,
        rarity="Restricted",
        souvenir=True,
    )
    return (
        normal_input,
        souvenir_input,
        _skin(NORMAL_KNIGHT_FN, rarity="Classified"),
        _skin(NORMAL_KNIGHT_MW, rarity="Classified"),
        _skin(
            SOUVENIR_KNIGHT_FN,
            rarity="Classified",
            souvenir=True,
        ),
        _skin(
            SOUVENIR_KNIGHT_MW,
            rarity="Classified",
            souvenir=True,
        ),
    )


def _construct(
    inputs: list[TradeUpEnrichedInput],
    *,
    catalog: tuple[SkinMetadata, ...] | None = None,
    config: RecipeSolverConfig | None = None,
):  # type: ignore[no-untyped-def]
    return construct_scanner_recipe_selections(
        enriched_inputs=inputs,
        canonical_skins=catalog or _catalog(),
        solver_config=config or _config(),
    )


def _names(selection) -> list[str]:  # type: ignore[no-untyped-def]
    return [
        result.output_market_hash_name
        for result in selection.recipe.tradeup_results
    ]


def test_raw_pinned_catalog_reproduces_previous_four_name_knight_defect() -> None:
    resolver = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)

    outputs = build_output_candidates_by_collection(
        list(resolver.skins),
        "Restricted",
    )[COBBLESTONE]

    assert [
        candidate.market_hash_name
        for candidate in outputs
        if "M4A1-S | Knight" in candidate.market_hash_name
    ] == [
        NORMAL_KNIGHT_FN,
        NORMAL_KNIGHT_MW,
        SOUVENIR_KNIGHT_FN,
        SOUVENIR_KNIGHT_MW,
    ]


@pytest.mark.parametrize("souvenir_count", [0, 5, 10])
def test_normal_souvenir_and_mixed_inputs_produce_only_normal_outputs(
    souvenir_count: int,
) -> None:
    catalog = _catalog()
    normal_skin, souvenir_skin = catalog[:2]
    inputs = [
        _enriched(
            index,
            souvenir_skin if index < souvenir_count else normal_skin,
        )
        for index in range(10)
    ]

    selections = _construct(inputs, catalog=catalog)

    assert len(selections) == 1
    assert _names(selections[0]) == [NORMAL_KNIGHT_FN, NORMAL_KNIGHT_MW]
    assert [item.souvenir for item in selections[0].recipe.input_items].count(True) == (
        souvenir_count
    )


def test_knight_regression_with_pinned_catalog_returns_normal_variants_only() -> None:
    resolver = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    normal = next(skin for skin in resolver.skins if skin.market_hash_name == NORMAL_INPUT)
    souvenir = next(
        skin for skin in resolver.skins if skin.market_hash_name == SOUVENIR_INPUT
    )
    inputs = [
        _enriched(index, normal if index < 5 else souvenir)
        for index in range(10)
    ]

    selections = _construct(inputs, catalog=resolver.skins)

    assert len(selections) == 1
    assert _names(selections[0]) == [NORMAL_KNIGHT_FN, NORMAL_KNIGHT_MW]
    assert not any(
        name.startswith("Souvenir ") for name in _names(selections[0])
    )


def test_souvenir_canonical_metadata_remains_exactly_resolvable_as_input() -> None:
    resolver = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    metadata = resolver.resolve(SOUVENIR_INPUT)

    assert metadata is not None
    assert metadata.market_hash_name == SOUVENIR_INPUT
    assert resolver.resolve(SOUVENIR_INPUT.removeprefix("Souvenir ")) is not metadata


def test_canonical_catalog_is_not_mutated_by_projection() -> None:
    catalog = _catalog()
    before = tuple(catalog)
    souvenir = catalog[1]

    _construct([_enriched(index, souvenir) for index in range(10)], catalog=catalog)

    assert catalog == before
    assert catalog[1].souvenir is True
    assert catalog[4].souvenir is True


def test_target_souvenir_filters_candidate_owned_facts_before_projection() -> None:
    normal, souvenir = _catalog()[:2]
    inputs = [
        *[_enriched(index, normal) for index in range(10)],
        *[_enriched(index + 10, souvenir) for index in range(10)],
    ]

    normal_selection = _construct(
        inputs,
        config=_config(target_souvenir=False),
    )[0]
    souvenir_selection = _construct(
        inputs,
        config=_config(target_souvenir=True),
    )[0]

    assert all(not item.souvenir for item in normal_selection.recipe.input_items)
    assert all(item.souvenir for item in souvenir_selection.recipe.input_items)
    assert _names(souvenir_selection) == [NORMAL_KNIGHT_FN, NORMAL_KNIGHT_MW]


def test_stattrak_remains_separate_and_uses_matching_normal_output() -> None:
    normal_input = _skin(NORMAL_INPUT, rarity="Restricted")
    stattrak_input = _skin(
        "StatTrak™ CZ75-Auto | Chalice (Factory New)",
        rarity="Restricted",
        stattrak=True,
    )
    normal_output = _skin(NORMAL_KNIGHT_FN, rarity="Classified")
    stattrak_output = _skin(
        "StatTrak™ M4A1-S | Knight (Factory New)",
        rarity="Classified",
        stattrak=True,
    )
    souvenir_stattrak_output = _skin(
        "Synthetic impossible combined output",
        rarity="Classified",
        stattrak=True,
        souvenir=True,
    )
    catalog = (
        normal_input,
        stattrak_input,
        normal_output,
        stattrak_output,
        souvenir_stattrak_output,
    )
    inputs = [
        *[_enriched(index, normal_input) for index in range(10)],
        *[_enriched(index + 10, stattrak_input) for index in range(10)],
    ]

    selections = _construct(inputs, catalog=catalog)

    assert len(selections) == 2
    assert _names(selections[0]) == [NORMAL_KNIGHT_FN]
    assert _names(selections[1]) == [
        "StatTrak™ M4A1-S | Knight (Factory New)"
    ]
    assert all(not item.stattrak for item in selections[0].recipe.input_items)
    assert all(item.stattrak for item in selections[1].recipe.input_items)


def test_five_normal_and_five_stattrak_inputs_do_not_mix() -> None:
    normal_input = _skin(NORMAL_INPUT, rarity="Restricted")
    stattrak_input = _skin(
        "StatTrak™ CZ75-Auto | Chalice (Factory New)",
        rarity="Restricted",
        stattrak=True,
    )
    catalog = (
        normal_input,
        stattrak_input,
        _skin(NORMAL_KNIGHT_FN, rarity="Classified"),
        _skin(
            "StatTrak™ M4A1-S | Knight (Factory New)",
            rarity="Classified",
            stattrak=True,
        ),
    )
    inputs = [
        *[_enriched(index, normal_input) for index in range(5)],
        *[_enriched(index + 5, stattrak_input) for index in range(5)],
    ]

    assert _construct(inputs, catalog=catalog) == []


def test_output_eligibility_treats_souvenir_and_stattrak_separately() -> None:
    normal = _skin(NORMAL_KNIGHT_FN, rarity="Classified")
    souvenir = replace(normal, market_hash_name=SOUVENIR_KNIGHT_FN, souvenir=True)
    stattrak = replace(
        normal,
        market_hash_name="StatTrak™ M4A1-S | Knight (Factory New)",
        stattrak=True,
    )

    assert is_current_standard_trade_up_output_eligible(
        skin=normal,
        result_stattrak=False,
    )
    assert not is_current_standard_trade_up_output_eligible(
        skin=souvenir,
        result_stattrak=False,
    )
    assert is_current_standard_trade_up_output_eligible(
        skin=stattrak,
        result_stattrak=True,
    )
    assert not is_current_standard_trade_up_output_eligible(
        skin=stattrak,
        result_stattrak=False,
    )


def test_candidate_owned_intrinsic_conflict_fails_closed() -> None:
    souvenir_skin = _catalog()[1]
    enriched = _enriched(0, souvenir_skin)
    conflicted = TradeUpEnrichedInput(
        candidate=enriched.candidate,
        input_item=replace(enriched.input_item, souvenir=False),
    )

    with pytest.raises(ScannerRecipeCompositionError):
        _construct([conflicted])


def test_duplicate_listing_provenance_fails_closed() -> None:
    normal = _catalog()[0]
    duplicated = [_enriched(0, normal), _enriched(0, normal)]

    with pytest.raises(ScannerRecipeCompositionError):
        _construct(duplicated)


def test_solver_projection_restores_exact_input_items(monkeypatch: pytest.MonkeyPatch) -> None:
    normal, souvenir = _catalog()[:2]
    inputs = [
        _enriched(index, normal if index < 5 else souvenir)
        for index in range(10)
    ]
    real_construct = composition_module.construct_recipe_selections
    captured: list[tuple[SkinMetadata, ...]] = []

    def capture(candidates, skins, config):  # type: ignore[no-untyped-def]
        captured.append(tuple(skins))
        return real_construct(candidates, skins, config)

    monkeypatch.setattr(composition_module, "construct_recipe_selections", capture)

    selection = _construct(inputs)[0]

    assert captured
    projected_input_names = {
        item.candidate.market_hash_name for item in inputs
    }
    assert all(
        skin.souvenir is False
        for skin in captured[0]
        if skin.market_hash_name in projected_input_names
    )
    assert selection.recipe.input_items == tuple(
        item.input_item
        for item in sorted(
            inputs,
            key=lambda value: (
                value.input_item.actual_float,
                value.input_item.price_cny,
                value.input_item.market_hash_name,
                value.candidate.listing_id,
            ),
        )
    )


def test_memory_error_from_solver_propagates_same_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = MemoryError("sentinel")

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(composition_module, "construct_recipe_selections", fail)
    normal = _catalog()[0]

    with pytest.raises(MemoryError) as exc_info:
        _construct([_enriched(index, normal) for index in range(10)])

    assert exc_info.value is sentinel


def test_source_contains_no_prefix_stripping_or_name_normalization() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "removeprefix" not in attributes
    assert "strip" not in attributes
    assert "casefold" not in attributes
    assert "lower" not in attributes
