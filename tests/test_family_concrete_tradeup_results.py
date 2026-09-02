"""Phase 16E — Finish-level concrete output tests."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from app.services.family_concrete_tradeup_results import (
    FamilyConcreteTradeupResultsError,
    build_concrete_family_tradeup_results,
)
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import StatTrakMode, build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.tradeup_engine import InputItem


def _row(
    *,
    collection: str,
    name: str,
    rarity: str,
    wear: str,
    min_float: float,
    max_float: float,
    stattrak: bool = False,
) -> SkinMetadata:
    prefix = "StatTrak™ " if stattrak else ""
    return SkinMetadata(
        market_hash_name=f"{prefix}{name} ({wear})",
        name=f"{prefix}{name}",
        weapon=name.split(" |", 1)[0],
        rarity=rarity,
        category=None,
        collection_name=collection,
        min_float=min_float,
        max_float=max_float,
        stattrak=stattrak,
        souvenir=False,
        paint_index=None,
        raw=None,
    )


def _input(
    *,
    collection: str,
    actual_float: float = 0.5,
    stattrak: bool = False,
    souvenir: bool = False,
) -> InputItem:
    prefix = "StatTrak™ " if stattrak else ("Souvenir " if souvenir else "")
    return InputItem(
        market_hash_name=f"{prefix}{collection} Input (Field-Tested)",
        collection_name=collection,
        rarity="Restricted",
        actual_float=actual_float,
        min_float=0.0,
        max_float=1.0,
        price_cny=Decimal("1"),
        stattrak=stattrak,
        souvenir=souvenir,
    )


def _wear_rows(
    *,
    collection: str,
    name: str,
    min_float: float = 0.0,
    max_float: float = 1.0,
    stattrak: bool = False,
    wears: tuple[str, ...] = (
        "Factory New",
        "Minimal Wear",
        "Field-Tested",
        "Well-Worn",
        "Battle-Scarred",
    ),
) -> list[SkinMetadata]:
    return [
        _row(
            collection=collection,
            name=name,
            rarity="Classified",
            wear=wear,
            min_float=min_float,
            max_float=max_float,
            stattrak=stattrak,
        )
        for wear in wears
    ]


def test_wear_row_cardinality_does_not_change_finish_probability() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        [
            *_wear_rows(collection="A", name="AK-47 | X"),
            *_wear_rows(
                collection="A",
                name="M4A4 | Y",
                wears=("Factory New", "Minimal Wear"),
            ),
        ]
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    geometry = compute_recipe_family_geometry(family, finish_index=index)
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=geometry,
        finish_index=index,
        selected_input_items=tuple(
            _input(collection="A", actual_float=0.1) for _ in range(10)
        ),
    )
    assert tuple(outcome.exact_probability for outcome in concrete.outcomes) == (
        Fraction(1, 2),
        Fraction(1, 2),
    )


def test_a6_b4_finish_probabilities_are_exact() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        [
            *_wear_rows(collection="A", name="AK-47 | X"),
            *_wear_rows(collection="A", name="M4A4 | Y"),
            *_wear_rows(collection="B", name="AWP | Z"),
        ]
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 6), ("B", 4)),
    )
    geometry = compute_recipe_family_geometry(family, finish_index=index)
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=geometry,
        finish_index=index,
        selected_input_items=(
            *tuple(_input(collection="A") for _ in range(6)),
            *tuple(_input(collection="B") for _ in range(4)),
        ),
    )
    assert sorted(outcome.exact_probability for outcome in concrete.outcomes) == [
        Fraction(3, 10),
        Fraction(3, 10),
        Fraction(2, 5),
    ]
    assert sum(
        (outcome.exact_probability for outcome in concrete.outcomes),
        start=Fraction(0),
    ) == Fraction(1)


def test_same_average_maps_through_each_finish_range() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        [
            *_wear_rows(
                collection="A",
                name="AK-47 | Narrow",
                min_float=0.0,
                max_float=0.14,
                wears=("Factory New", "Minimal Wear"),
            ),
            *_wear_rows(
                collection="A",
                name="M4A4 | Wide",
                min_float=0.0,
                max_float=1.0,
            ),
        ]
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=compute_recipe_family_geometry(family, finish_index=index),
        finish_index=index,
        selected_input_items=tuple(
            _input(collection="A", actual_float=0.5) for _ in range(10)
        ),
    )
    outputs = {result.output_wear: result.output_float for result in concrete.tradeup_results}
    assert outputs["Minimal Wear"] == pytest.approx(0.07)
    assert outputs["Battle-Scarred"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("average", "expected_wear"),
    [
        (0.07, "Minimal Wear"),
        (0.15, "Field-Tested"),
        (0.38, "Well-Worn"),
        (0.45, "Battle-Scarred"),
    ],
)
def test_exact_wear_boundaries(average: float, expected_wear: str) -> None:
    index = StructuralOutputFinishIndex.from_skins(
        _wear_rows(collection="A", name="AK-47 | X")
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=compute_recipe_family_geometry(family, finish_index=index),
        finish_index=index,
        selected_input_items=tuple(
            _input(collection="A", actual_float=average) for _ in range(10)
        ),
    )
    assert concrete.tradeup_results[0].output_wear == expected_wear


def test_missing_finish_wear_mapping_fails_closed() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        _wear_rows(
            collection="A",
            name="AK-47 | X",
            wears=("Factory New",),
        )
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    with pytest.raises(FamilyConcreteTradeupResultsError):
        build_concrete_family_tradeup_results(
            family,
            geometry=compute_recipe_family_geometry(family, finish_index=index),
            finish_index=index,
            selected_input_items=tuple(
                _input(collection="A", actual_float=0.5) for _ in range(10)
            ),
        )


def test_mixed_normal_souvenir_provenance_produces_non_souvenir_output() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        _wear_rows(collection="A", name="AK-47 | X")
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    items = tuple(
        _input(collection="A", souvenir=index_value % 2 == 0)
        for index_value in range(10)
    )
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=compute_recipe_family_geometry(family, finish_index=index),
        finish_index=index,
        selected_input_items=items,
    )
    assert {item.souvenir for item in items} == {False, True}
    assert all(
        not result.output_market_hash_name.startswith("Souvenir ")
        for result in concrete.tradeup_results
    )


def test_stattrak_family_resolves_exact_stattrak_output_name() -> None:
    index = StructuralOutputFinishIndex.from_skins(
        _wear_rows(
            collection="A",
            name="AK-47 | X",
            stattrak=True,
        )
    )
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.STATTRAK,
        collection_counts=(("A", 10),),
    )
    concrete = build_concrete_family_tradeup_results(
        family,
        geometry=compute_recipe_family_geometry(family, finish_index=index),
        finish_index=index,
        selected_input_items=tuple(
            _input(collection="A", stattrak=True) for _ in range(10)
        ),
    )
    assert concrete.tradeup_results[0].output_market_hash_name.startswith(
        "StatTrak™ "
    )
