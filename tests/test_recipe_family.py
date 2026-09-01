"""Phase 16B — RecipeFamily domain and lazy generator tests."""

from __future__ import annotations

from itertools import islice
from math import comb
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.recipe_family import (
    MAX_DISTINCT_COLLECTIONS_PER_FAMILY,
    ProductiveInputRarities,
    RecipeFamily,
    RecipeFamilyGenerator,
    RecipeFamilyIdentityError,
    StatTrakMode,
    build_recipe_family,
    compute_recipe_family_hash,
    count_recipe_families,
    get_next_rarity,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.structural_output_finish import StructuralOutputFinishIndex

ROOT = Path(__file__).resolve().parent.parent


def test_build_recipe_family_basic_invariants() -> None:
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("Collection A", 6), ("Collection B", 4)),
    )
    assert family.family_spec_version == 1
    assert family.input_rarity == "Restricted"
    assert family.stattrak_mode is StatTrakMode.NORMAL
    assert family.collection_counts == (
        ("Collection A", 6),
        ("Collection B", 4),
    )
    assert len(family.family_hash) == 64
    assert family.family_key == family.family_hash[:24]


def test_collection_counts_are_sorted_ascending_by_name() -> None:
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("Z", 5), ("A", 5)),
    )
    assert family.collection_counts == (("A", 5), ("Z", 5))


@pytest.mark.parametrize(
    "counts",
    [
        (("A", 5), ("A", 5)),
        (("A", 5), ("B", 4)),
        (("A", 0), ("B", 10)),
        (),
        (("A", 1), ("B", 1), ("C", 1), ("D", 7)),
    ],
)
def test_invalid_collection_counts_rejected(
    counts: tuple[tuple[str, int], ...],
) -> None:
    with pytest.raises(RecipeFamilyIdentityError):
        build_recipe_family(
            input_rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=counts,
        )


def test_stattrak_mode_distinct_families() -> None:
    normal = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    stattrak = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.STATTRAK,
        collection_counts=(("A", 10),),
    )
    assert normal.family_hash != stattrak.family_hash


def test_input_rarity_is_one_of_productive_rarities() -> None:
    for rarity in ProductiveInputRarities:
        family = build_recipe_family(
            input_rarity=rarity,
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=(("A", 10),),
        )
        assert family.input_rarity == rarity


def test_unsupported_input_rarity_rejected() -> None:
    with pytest.raises(RecipeFamilyIdentityError):
        build_recipe_family(
            input_rarity="Covert",
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=(("A", 10),),
        )


def test_family_hash_changes_with_collection_composition() -> None:
    a = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 6), ("B", 4)),
    )
    b = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 4), ("B", 6)),
    )
    assert a.family_hash != b.family_hash


def test_family_hash_is_stable_under_reordering_input() -> None:
    a = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 6), ("B", 4)),
    )
    b = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("B", 4), ("A", 6)),
    )
    assert a.family_hash == b.family_hash


def test_direct_family_rejects_noncanonical_hash() -> None:
    with pytest.raises(RecipeFamilyIdentityError):
        RecipeFamily(
            family_spec_version=1,
            input_rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=(("A", 10),),
            family_hash="0" * 64,
            family_key="0" * 24,
        )


def test_get_next_rarity() -> None:
    assert get_next_rarity("Consumer Grade") == "Industrial Grade"
    assert get_next_rarity("Industrial Grade") == "Mil-Spec Grade"
    assert get_next_rarity("Mil-Spec Grade") == "Restricted"
    assert get_next_rarity("Restricted") == "Classified"
    assert get_next_rarity("Classified") == "Covert"
    assert get_next_rarity("Covert") is None
    with pytest.raises(ValueError):
        get_next_rarity("Unknown")


def test_count_recipe_families_formulas() -> None:
    assert count_recipe_families(0) == 0
    with pytest.raises(RecipeFamilyIdentityError):
        count_recipe_families(-1)
    with pytest.raises(RecipeFamilyIdentityError):
        count_recipe_families(5, max_distinct=0)
    with pytest.raises(RecipeFamilyIdentityError):
        count_recipe_families(5, max_distinct=4)
    for c in range(1, 10):
        assert count_recipe_families(c, max_distinct=1) == c
    for c in range(2, 12):
        expected = c + comb(c, 2) * 9
        assert count_recipe_families(c, max_distinct=2) == expected


def test_count_recipe_families_k3_authoritative_values() -> None:
    frozen = {
        38: 310061,
        44: 485342,
        86: 3717221,
        76: 2556526,
        63: 1447236,
    }
    for collection_count, expected in frozen.items():
        assert count_recipe_families(collection_count) == expected
    total = (
        310061
        + 485342
        + 3717221
        + 485342
        + 2556526
        + 485342
        + 1447236
        + 485342
    )
    assert total == 9_972_412


def test_family_field_set_excludes_derived_and_market_fields() -> None:
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 10),),
    )
    fields = {f.name for f in family.__dataclass_fields__.values()}
    for forbidden in (
        "represented_outputs",
        "represented_output_finishes",
        "souvenir_inclusion",
        "goods_id",
        "market_hash_name",
        "price_cny",
    ):
        assert forbidden not in fields


def test_compute_recipe_family_hash_is_deterministic() -> None:
    h1 = compute_recipe_family_hash(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("A", 6), ("B", 4)),
    )
    h2 = compute_recipe_family_hash(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("B", 4), ("A", 6)),
    )
    assert h1 == h2


def test_max_distinct_collections_constant_is_three() -> None:
    assert MAX_DISTINCT_COLLECTIONS_PER_FAMILY == 3


def _pinned_generator(
    input_rarity: str,
    stattrak_mode: StatTrakMode,
) -> RecipeFamilyGenerator:
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        ROOT / "data" / "metadata" / "skin_metadata_v1.json"
    )
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    return RecipeFamilyGenerator.from_catalogs(
        skins=metadata.skins,
        identity_resolver=identity,
        finish_index=finish_index,
        input_rarity=input_rarity,
        stattrak_mode=stattrak_mode,
    )


def test_pinned_eligible_collection_and_family_counts() -> None:
    frozen = (
        ("Consumer Grade", StatTrakMode.NORMAL, 38, 310061),
        ("Industrial Grade", StatTrakMode.NORMAL, 44, 485342),
        ("Mil-Spec Grade", StatTrakMode.NORMAL, 86, 3717221),
        ("Mil-Spec Grade", StatTrakMode.STATTRAK, 44, 485342),
        ("Restricted", StatTrakMode.NORMAL, 76, 2556526),
        ("Restricted", StatTrakMode.STATTRAK, 44, 485342),
        ("Classified", StatTrakMode.NORMAL, 63, 1447236),
        ("Classified", StatTrakMode.STATTRAK, 44, 485342),
    )
    total = 0
    for rarity, mode, expected_collections, expected_families in frozen:
        generator = _pinned_generator(rarity, mode)
        assert len(generator.stratum.eligible_collections) == expected_collections
        assert generator.count() == expected_families
        total += generator.count()
    assert total == 9_972_412


def test_lazy_generator_order_and_prefix() -> None:
    generator = _pinned_generator("Restricted", StatTrakMode.NORMAL)
    iterator = generator.iter_families()
    assert iter(iterator) is iterator
    first_five = list(islice(iterator, 5))
    assert len(first_five) == 5
    assert [f.collection_counts[0][0] for f in first_five] == list(
        generator.stratum.eligible_collections[:5]
    )


def test_two_collection_composition_order_is_lexicographic() -> None:
    generator = _pinned_generator("Restricted", StatTrakMode.NORMAL)
    c = len(generator.stratum.eligible_collections)
    iterator = generator.iter_families()
    first_pair_families = list(islice(iterator, c, c + 9))
    expected = [
        (
            (generator.stratum.eligible_collections[0], i),
            (generator.stratum.eligible_collections[1], 10 - i),
        )
        for i in range(1, 10)
    ]
    assert [f.collection_counts for f in first_pair_families] == expected


def test_generator_reiterable_by_new_iterator() -> None:
    generator = _pinned_generator("Classified", StatTrakMode.STATTRAK)
    first_a = list(islice(generator.iter_families(), 5))
    first_b = list(islice(generator.iter_families(), 5))
    assert [f.family_hash for f in first_a] == [f.family_hash for f in first_b]
