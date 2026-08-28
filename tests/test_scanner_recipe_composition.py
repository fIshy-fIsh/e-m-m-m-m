from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path

import pytest

import app.services.scanner_recipe_composition as composition_module
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import build_output_candidates_by_collection
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeEnumerationConfig,
    RecipeEnumerationDiagnostics,
    RecipeEnumerationResult,
    RecipeSolverConfig,
)
from app.services.scanner_recipe_composition import (
    ScannerRecipeBucketDiagnostics,
    ScannerRecipeCompositionDiagnostics,
    ScannerRecipeCompositionError,
    ScannerRecipeCompositionResult,
    construct_scanner_recipe_selections,
    enumerate_scanner_recipe_selections,
    is_current_standard_trade_up_output_eligible,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem, TradeupResult

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


def _enumerate(
    inputs: list[TradeUpEnrichedInput],
    *,
    catalog: tuple[SkinMetadata, ...] | None = None,
    config: RecipeSolverConfig | None = None,
    candidate_limit: int = 2,
    state_limit: int = 256,
) -> ScannerRecipeCompositionResult:
    return enumerate_scanner_recipe_selections(
        enriched_inputs=inputs,
        canonical_skins=catalog or _catalog(),
        solver_config=config or _config(),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=candidate_limit,
            max_candidate_states_explored=state_limit,
        ),
    )


def _two_mode_inputs(
    *,
    normal_count: int = 10,
    stattrak_count: int = 10,
) -> tuple[list[TradeUpEnrichedInput], tuple[SkinMetadata, ...]]:
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
        *[_enriched(index, normal_input) for index in range(normal_count)],
        *[
            _enriched(index + normal_count, stattrak_input)
            for index in range(stattrak_count)
        ],
    ]
    return inputs, catalog


def _names(selection) -> list[str]:  # type: ignore[no-untyped-def]
    return [
        result.output_market_hash_name
        for result in selection.recipe.tradeup_results
    ]


def _core_diagnostics(
    *,
    selections: tuple[ConstructedRecipeSelection, ...],
    states_explored: int,
    baseline_state_rejected: bool = False,
) -> RecipeEnumerationDiagnostics:
    return RecipeEnumerationDiagnostics(
        eligible_input_count=10,
        retained_input_count=10,
        theoretical_radius_one_states=max(1, states_explored),
        states_explored=states_explored,
        raw_candidates_found=len(selections),
        unique_candidates_returned=len(selections),
        duplicates_suppressed=0,
        engine_rejected_states=int(baseline_state_rejected),
        baseline_state_rejected=baseline_state_rejected,
        candidate_limit_reached=False,
        exploration_limit_reached=False,
    )


def _projected_selection(
    values: list[TradeUpEnrichedInput],
    listing_ids: list[str],
    *,
    label: str,
) -> ConstructedRecipeSelection:
    index = {value.candidate.listing_id: value for value in values}
    items = tuple(
        replace(index[listing_id].input_item, souvenir=False)
        for listing_id in listing_ids
    )
    return ConstructedRecipeSelection(
        recipe=ConstructedRecipe(
            input_items=items,
            tradeup_results=(
                TradeupResult(
                    output_market_hash_name=label,
                    probability=1.0,
                    output_float=0.01,
                    output_wear="Factory New",
                    estimated_price_cny=Decimal("0"),
                    expected_value_contribution=Decimal("0"),
                ),
            ),
            paint_seeds=(),
        ),
        selected_listing_ids=tuple(listing_ids),
    )


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


def test_composition_public_signatures_and_dtos_are_locked() -> None:
    legacy_parameters = list(
        signature(construct_scanner_recipe_selections).parameters.values()
    )
    assert [parameter.name for parameter in legacy_parameters] == [
        "enriched_inputs",
        "canonical_skins",
        "solver_config",
    ]
    assert all(
        parameter.kind is Parameter.KEYWORD_ONLY
        for parameter in legacy_parameters
    )
    assert (
        signature(construct_scanner_recipe_selections).return_annotation
        == "list[ConstructedRecipeSelection]"
    )

    bounded_parameters = list(
        signature(enumerate_scanner_recipe_selections).parameters.values()
    )
    assert [parameter.name for parameter in bounded_parameters] == [
        "enriched_inputs",
        "canonical_skins",
        "solver_config",
        "enumeration_config",
    ]
    assert all(
        parameter.kind is Parameter.KEYWORD_ONLY
        for parameter in bounded_parameters
    )
    assert (
        signature(enumerate_scanner_recipe_selections).return_annotation
        == "ScannerRecipeCompositionResult"
    )

    diagnostics = ScannerRecipeCompositionDiagnostics(
        aggregate_candidate_limit=1,
        aggregate_state_limit=1,
        active_bucket_count=0,
        participating_bucket_count=0,
        buckets=(),
        returned_candidates=0,
        states_explored=0,
    )
    result = ScannerRecipeCompositionResult(
        selections=(),
        diagnostics=diagnostics,
    )
    bucket = ScannerRecipeBucketDiagnostics(
        stattrak=False,
        candidate_quota=1,
        state_quota=1,
        returned_candidates=0,
        states_explored=0,
        baseline_state_rejected=False,
    )
    with pytest.raises(FrozenInstanceError):
        result.selections = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bucket.state_quota = 2  # type: ignore[misc]
    assert repr(result).startswith("<")
    assert repr(diagnostics).startswith("<")
    assert repr(bucket).startswith("<")


def test_legacy_and_bounded_paths_use_separate_core_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = _catalog()[0]
    inputs = [_enriched(index, normal) for index in range(10)]
    real_legacy = composition_module.construct_recipe_selections
    real_bounded = composition_module.enumerate_recipe_selections
    calls = {"legacy": 0, "bounded": 0}

    def capture_legacy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["legacy"] += 1
        return real_legacy(*args, **kwargs)

    def capture_bounded(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["bounded"] += 1
        return real_bounded(*args, **kwargs)

    monkeypatch.setattr(
        composition_module,
        "construct_recipe_selections",
        capture_legacy,
    )
    monkeypatch.setattr(
        composition_module,
        "enumerate_recipe_selections",
        capture_bounded,
    )

    legacy = _construct(inputs)
    assert len(legacy) == 1
    assert calls == {"legacy": 1, "bounded": 0}

    bounded = _enumerate(inputs)
    assert len(bounded.selections) == 1
    assert calls == {"legacy": 1, "bounded": 1}


def test_real_bounded_composition_returns_two_exact_rehydrated_candidates() -> None:
    normal, souvenir = _catalog()[:2]
    inputs = [
        _enriched(index, souvenir if index in {0, 5, 10} else normal)
        for index in range(11)
    ]

    result = _enumerate(inputs, candidate_limit=2, state_limit=256)

    assert [selection.selected_listing_ids for selection in result.selections] == [
        tuple(f"listing-{index}" for index in range(10)),
        (*tuple(f"listing-{index}" for index in range(9)), "listing-10"),
    ]
    original_by_id = {
        value.candidate.listing_id: value.input_item for value in inputs
    }
    for selection in result.selections:
        assert selection.recipe.input_items == tuple(
            original_by_id[listing_id]
            for listing_id in selection.selected_listing_ids
        )
    assert result.diagnostics.returned_candidates == 2
    assert result.diagnostics.states_explored == 2
    assert result.diagnostics.returned_candidates <= 2
    assert result.diagnostics.states_explored <= 256


def test_real_two_bucket_composition_respects_aggregate_bounds() -> None:
    inputs, catalog = _two_mode_inputs()

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=2,
        state_limit=3,
    )

    assert len(result.selections) == 2
    assert [
        (bucket.candidate_quota, bucket.state_quota)
        for bucket in result.diagnostics.buckets
    ] == [(1, 2), (1, 1)]
    assert [
        (bucket.returned_candidates, bucket.states_explored)
        for bucket in result.diagnostics.buckets
    ] == [(1, 1), (1, 1)]
    assert result.diagnostics.returned_candidates == 2
    assert result.diagnostics.states_explored == 2
    assert result.diagnostics.returned_candidates <= 2
    assert result.diagnostics.states_explored <= 3


@pytest.mark.parametrize(
    ("candidate_limit", "state_limit", "expected"),
    [
        (6, 256, ((3, 128), (3, 128))),
        (5, 255, ((3, 128), (2, 127))),
        (2, 3, ((1, 2), (1, 1))),
    ],
)
def test_aggregate_quota_split_across_two_active_buckets(
    monkeypatch: pytest.MonkeyPatch,
    candidate_limit: int,
    state_limit: int,
    expected: tuple[tuple[int, int], tuple[int, int]],
) -> None:
    inputs, catalog = _two_mode_inputs()
    calls: list[tuple[int, int, bool]] = []

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        calls.append(
            (
                enumeration_config.max_recipe_candidates_returned,
                enumeration_config.max_candidate_states_explored,
                config.target_stattrak,
            )
        )
        return RecipeEnumerationResult(
            selections=(),
            diagnostics=_core_diagnostics(
                selections=(),
                states_explored=0,
            ),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=candidate_limit,
        state_limit=state_limit,
    )

    assert [(candidate, state) for candidate, state, _ in calls] == list(expected)
    assert [stattrak for _, _, stattrak in calls] == [False, True]
    assert [
        (bucket.candidate_quota, bucket.state_quota)
        for bucket in result.diagnostics.buckets
    ] == list(expected)
    assert result.diagnostics.active_bucket_count == 2
    assert result.diagnostics.participating_bucket_count == 2


def test_candidate_cap_one_calls_only_first_active_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, catalog = _two_mode_inputs()
    calls: list[tuple[int, int, bool]] = []

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        calls.append(
            (
                enumeration_config.max_recipe_candidates_returned,
                enumeration_config.max_candidate_states_explored,
                config.target_stattrak,
            )
        )
        return RecipeEnumerationResult(
            selections=(),
            diagnostics=_core_diagnostics(selections=(), states_explored=0),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=1,
        state_limit=256,
    )

    assert calls == [(1, 256, False)]
    assert [
        (bucket.stattrak, bucket.candidate_quota, bucket.state_quota)
        for bucket in result.diagnostics.buckets
    ] == [(False, 1, 256), (True, 0, 0)]
    assert result.selections == ()
    assert result.diagnostics.returned_candidates <= 1
    assert result.diagnostics.states_explored <= 256


def test_only_stattrak_active_receives_full_aggregate_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, catalog = _two_mode_inputs(normal_count=0, stattrak_count=10)
    calls: list[tuple[int, int, bool]] = []

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        calls.append(
            (
                enumeration_config.max_recipe_candidates_returned,
                enumeration_config.max_candidate_states_explored,
                config.target_stattrak,
            )
        )
        return RecipeEnumerationResult(
            selections=(),
            diagnostics=_core_diagnostics(selections=(), states_explored=0),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=6,
        state_limit=256,
    )

    assert calls == [(6, 256, True)]
    assert result.diagnostics.active_bucket_count == 1
    assert result.diagnostics.participating_bucket_count == 1
    assert result.diagnostics.buckets == (
        ScannerRecipeBucketDiagnostics(
            stattrak=True,
            candidate_quota=6,
            state_quota=256,
            returned_candidates=0,
            states_explored=0,
            baseline_state_rejected=False,
        ),
    )


def test_no_active_bucket_returns_zero_diagnostics_without_core_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = _catalog()[0]
    calls = 0

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("core must not be called")

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", fail)

    result = _enumerate([_enriched(index, normal) for index in range(9)])

    assert calls == 0
    assert result.selections == ()
    assert result.diagnostics == ScannerRecipeCompositionDiagnostics(
        aggregate_candidate_limit=2,
        aggregate_state_limit=256,
        active_bucket_count=0,
        participating_bucket_count=0,
        buckets=(),
        returned_candidates=0,
        states_explored=0,
    )


def test_duplicate_provenance_preflight_makes_no_bounded_core_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = _catalog()[0]
    duplicated = [_enriched(index, normal) for index in range(10)]
    duplicated.append(duplicated[0])
    calls = 0

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("core must not be called")

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", fail)

    with pytest.raises(ScannerRecipeCompositionError):
        _enumerate(duplicated)

    assert calls == 0


def test_all_enumerated_candidates_are_exactly_rehydrated_with_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal, souvenir = _catalog()[:2]
    inputs = [
        _enriched(index, souvenir if index in {0, 5, 10} else normal)
        for index in range(11)
    ]
    first_ids = [f"listing-{index}" for index in range(10)]
    second_ids = [f"listing-{index}" for index in range(9)] + ["listing-10"]
    projected = (
        _projected_selection(inputs, first_ids, label="normal baseline"),
        _projected_selection(inputs, second_ids, label="normal alt1"),
    )
    projected_items = {
        id(item)
        for selection in projected
        for item in selection.recipe.input_items
    }

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        assert all(
            skin.souvenir is False
            for skin in skins
            if skin.rarity == "Restricted"
        )
        return RecipeEnumerationResult(
            selections=projected,
            diagnostics=_core_diagnostics(
                selections=projected,
                states_explored=2,
            ),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(inputs)
    original_by_id = {
        value.candidate.listing_id: value.input_item for value in inputs
    }

    assert len(result.selections) == 2
    for selection, expected_ids in zip(
        result.selections,
        (first_ids, second_ids),
        strict=True,
    ):
        assert selection.selected_listing_ids == tuple(expected_ids)
        assert selection.recipe.input_items == tuple(
            original_by_id[listing_id] for listing_id in expected_ids
        )
        assert all(
            id(item) not in projected_items
            for item in selection.recipe.input_items
        )
    first_shared = result.selections[0].recipe.input_items[0]
    second_shared = result.selections[1].recipe.input_items[0]
    assert first_shared is second_shared
    assert first_shared is inputs[0].input_item
    assert first_shared.souvenir is True
    assert result.selections[1].recipe.input_items[-1] is inputs[10].input_item
    assert result.selections[1].recipe.input_items[-1].souvenir is True
    assert result.selections[0].recipe.tradeup_results is projected[0].recipe.tradeup_results
    assert result.selections[1].recipe.tradeup_results is projected[1].recipe.tradeup_results


def test_both_valid_baselines_precede_depth_interleaved_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, catalog = _two_mode_inputs(normal_count=11, stattrak_count=11)
    normal = inputs[:11]
    stattrak = inputs[11:]
    per_mode = {
        False: (
            _projected_selection(
                normal,
                [item.candidate.listing_id for item in normal[:10]],
                label="normal baseline",
            ),
            _projected_selection(
                normal,
                [item.candidate.listing_id for item in normal[:9]]
                + [normal[10].candidate.listing_id],
                label="normal alt1",
            ),
        ),
        True: (
            _projected_selection(
                stattrak,
                [item.candidate.listing_id for item in stattrak[:10]],
                label="stattrak baseline",
            ),
            _projected_selection(
                stattrak,
                [item.candidate.listing_id for item in stattrak[:9]]
                + [stattrak[10].candidate.listing_id],
                label="stattrak alt1",
            ),
        ),
    }

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        selections = per_mode[config.target_stattrak]
        return RecipeEnumerationResult(
            selections=selections,
            diagnostics=_core_diagnostics(
                selections=selections,
                states_explored=2,
            ),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=4,
        state_limit=4,
    )

    assert [_names(selection)[0] for selection in result.selections] == [
        "normal baseline",
        "stattrak baseline",
        "normal alt1",
        "stattrak alt1",
    ]


def test_valid_baseline_precedes_other_bucket_rejected_baseline_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, catalog = _two_mode_inputs(normal_count=12, stattrak_count=11)
    normal = inputs[:12]
    stattrak = inputs[12:]
    normal_alternatives = (
        _projected_selection(
            normal,
            [item.candidate.listing_id for item in normal[:9]]
            + [normal[10].candidate.listing_id],
            label="normal alt1",
        ),
        _projected_selection(
            normal,
            [item.candidate.listing_id for item in normal[:9]]
            + [normal[11].candidate.listing_id],
            label="normal alt2",
        ),
    )
    stattrak_selections = (
        _projected_selection(
            stattrak,
            [item.candidate.listing_id for item in stattrak[:10]],
            label="stattrak baseline",
        ),
        _projected_selection(
            stattrak,
            [item.candidate.listing_id for item in stattrak[:9]]
            + [stattrak[10].candidate.listing_id],
            label="stattrak alt1",
        ),
    )

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        if config.target_stattrak:
            selections = stattrak_selections
            baseline_rejected = False
        else:
            selections = normal_alternatives
            baseline_rejected = True
        return RecipeEnumerationResult(
            selections=selections,
            diagnostics=_core_diagnostics(
                selections=selections,
                states_explored=3 if baseline_rejected else 2,
                baseline_state_rejected=baseline_rejected,
            ),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=4,
        state_limit=5,
    )

    assert [_names(selection)[0] for selection in result.selections] == [
        "stattrak baseline",
        "normal alt1",
        "stattrak alt1",
        "normal alt2",
    ]
    assert [
        bucket.baseline_state_rejected
        for bucket in result.diagnostics.buckets
    ] == [True, False]
    assert result.diagnostics.returned_candidates == 4
    assert result.diagnostics.states_explored == 5


def test_actual_diagnostics_sum_core_usage_not_allocated_quotas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, catalog = _two_mode_inputs()
    explored = {False: 17, True: 8}

    def capture(candidates, skins, config, *, enumeration_config):  # type: ignore[no-untyped-def]
        source = inputs[:10] if not config.target_stattrak else inputs[10:]
        selection = _projected_selection(
            source,
            [item.candidate.listing_id for item in source],
            label="normal" if not config.target_stattrak else "stattrak",
        )
        selections = (selection,)
        return RecipeEnumerationResult(
            selections=selections,
            diagnostics=_core_diagnostics(
                selections=selections,
                states_explored=explored[config.target_stattrak],
            ),
        )

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", capture)

    result = _enumerate(
        inputs,
        catalog=catalog,
        candidate_limit=6,
        state_limit=256,
    )

    assert result.diagnostics.states_explored == 25
    assert result.diagnostics.returned_candidates == 2
    assert [bucket.states_explored for bucket in result.diagnostics.buckets] == [17, 8]
    assert [bucket.returned_candidates for bucket in result.diagnostics.buckets] == [1, 1]
    assert result.diagnostics.returned_candidates <= 6
    assert result.diagnostics.states_explored <= 256


def test_bounded_composition_rejects_invalid_aggregate_config_type_before_core_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("core must not be called")

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", fail)
    normal = _catalog()[0]

    with pytest.raises(ScannerRecipeCompositionError):
        enumerate_scanner_recipe_selections(
            enriched_inputs=[_enriched(index, normal) for index in range(10)],
            canonical_skins=_catalog(),
            solver_config=_config(),
            enumeration_config=None,  # type: ignore[arg-type]
        )

    assert calls == 0


def test_bounded_composition_memory_error_propagates_same_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = MemoryError("bounded sentinel")

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", fail)
    normal = _catalog()[0]

    with pytest.raises(MemoryError) as exc_info:
        _enumerate([_enriched(index, normal) for index in range(10)])

    assert exc_info.value is sentinel


def test_bounded_composition_unexpected_core_exception_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("unexpected sentinel")

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise sentinel

    monkeypatch.setattr(composition_module, "enumerate_recipe_selections", fail)
    normal = _catalog()[0]

    with pytest.raises(RuntimeError) as exc_info:
        _enumerate([_enriched(index, normal) for index in range(10)])

    assert exc_info.value is sentinel


def test_source_contains_no_direct_tradeup_engine_or_financial_ordering() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "calculate_tradeup_results" not in called_names
    assert "calculate_opportunity_metrics" not in called_names
    assert "evaluate_opportunity" not in called_names


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
