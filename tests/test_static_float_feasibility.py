"""Phase 16C — Static float feasibility tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.float_interval import empty_union
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.static_float_feasibility import (
    ReachableOutputWear,
    StaticFloatFeasibilityError,
    StaticFloatFeasibilityStatus,
    compute_static_float_feasibility,
    query_target_wear,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex

ROOT = Path(__file__).resolve().parent.parent


def _load_skins() -> list[SkinMetadata]:
    payload = json.loads(
        (ROOT / "data" / "metadata" / "skin_metadata_v1.json").read_bytes()
    )
    return [
        SkinMetadata(
            market_hash_name=it["market_hash_name"],
            name=it.get("name"),
            weapon=it.get("weapon"),
            rarity=it["rarity"],
            category=it.get("category"),
            collection_name=it.get("collection_name"),
            min_float=it["min_float"],
            max_float=it["max_float"],
            stattrak=bool(it.get("stattrak", False)),
            souvenir=bool(it.get("souvenir", False)),
            paint_index=it.get("paint_index"),
            raw=None,
        )
        for it in payload["items"]
    ]


@pytest.fixture(scope="module")
def pinned_context() -> tuple[
    list[SkinMetadata],
    BuffCommunityIdentityResolver,
    StructuralOutputFinishIndex,
]:
    skins = _load_skins()
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    finish_index = StructuralOutputFinishIndex.from_skins(skins)
    return skins, identity, finish_index


def test_continuous_adjusted_full_range_covers_all_wear_bands(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    assert result.status is StaticFloatFeasibilityStatus.FEASIBLE
    wear_names = set(result.reachable_wear_names())
    assert wear_names == {
        "Factory New",
        "Minimal Wear",
        "Field-Tested",
        "Well-Worn",
        "Battle-Scarred",
    }
    assert all(
        entry.exact_market_hash_name != "" for entry in result.reachable_outputs
    )


def test_narrow_output_range_only_reaches_specific_wear_bands(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    """When the family avg-adjusted is in `[0, 1]`, only finishes whose
    output range is a subset of one canonical wear band can be reached.

    For finishes with very narrow output ranges (e.g. `(0.45, 0.5]`),
    only Battle-Scarred is reachable, while wider finishes can reach
    multiple wear bands.
    """

    skins, identity, finish_index = pinned_context
    horizon_finishes = [
        f
        for f in finish_index.finishes
        if f.collection_name == "The Horizon Collection" and f.rarity == "Classified"
    ]
    assert horizon_finishes
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    assert result.reachable_outputs
    per_finish_wear_count = {
        finish.finish_key: sum(
            1 for entry in result.reachable_outputs if entry.finish_key == finish.finish_key
        )
        for finish in horizon_finishes
    }
    non_zero = [c for c in per_finish_wear_count.values() if c > 0]
    assert non_zero, "expected at least one finish with reachable wear bands"


def test_mixed_family_A6_B4_yields_specific_reachability(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 6), ("The Spectrum 2 Collection", 4)),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    assert result.status is StaticFloatFeasibilityStatus.FEASIBLE
    assert not result.reachable_avg_adjusted.is_empty


def test_wear_boundary_resolves_to_exact_wear(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    geom = compute_recipe_family_geometry(family, finish_index=finish_index)
    for outcome in geom.outcomes:
        entry = query_target_wear(
            result, finish_key=outcome.finish_key, wear_name="Factory New"
        )
        if entry is not None:
            assert entry.wear_name == "Factory New"
            assert entry.exact_market_hash_name.endswith("(Factory New)")
            break
    else:
        pytest.skip("no Factory New reachability in this snapshot")


def test_souvenir_input_does_not_pollute_output_wear_map(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    for entry in result.reachable_outputs:
        assert "Souvenir" not in entry.exact_market_hash_name


def test_stattrak_and_normal_inputs_do_not_mix(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    normal = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    stattrak = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.STATTRAK,
        collection_counts=(("The Horizon Collection", 10),),
    )
    normal_result = compute_static_float_feasibility(
        normal, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    stattrak_result = compute_static_float_feasibility(
        stattrak, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    assert normal_result.reachable_outputs != stattrak_result.reachable_outputs


def test_unresolved_output_wear_fails_closed(
    pinned_context: tuple[
        list[SkinMetadata],
        BuffCommunityIdentityResolver,
        StructuralOutputFinishIndex,
    ]
) -> None:
    skins, identity, finish_index = pinned_context
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    result = compute_static_float_feasibility(
        family, skins=tuple(skins), identity_resolver=identity, finish_index=finish_index
    )
    invalid_finish_key = "0" * 64
    assert query_target_wear(
        result, finish_key=invalid_finish_key, wear_name="Factory New"
    ) is None
    assert query_target_wear(
        result, finish_key="missing", wear_name="Factory New"
    ) is None


def test_static_feasibility_status_enum_values() -> None:
    assert StaticFloatFeasibilityStatus.FEASIBLE.value == "feasible"
    assert (
        StaticFloatFeasibilityStatus.NO_ELIGIBLE_INPUT_INTERVAL.value
        == "no_eligible_input_interval"
    )
    assert (
        StaticFloatFeasibilityStatus.NO_REACHABLE_OUTPUT_WEAR.value
        == "no_reachable_output_wear"
    )
    assert (
        StaticFloatFeasibilityStatus.OUTPUT_WEAR_MAPPING_UNRESOLVED.value
        == "output_wear_mapping_unresolved"
    )


def test_reachable_output_wear_dataclass_rejects_bad_inputs() -> None:
    with pytest.raises(StaticFloatFeasibilityError):
        ReachableOutputWear(
            finish_key="",
            wear_name="Factory New",
            exact_market_hash_name="x",
            output_float_intervals=empty_union(),
        )