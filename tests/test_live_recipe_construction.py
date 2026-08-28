from __future__ import annotations

import ast
import asyncio
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.live_recipe_construction as construction_module
from app.services.live_metadata_catalog import (
    LiveCandidateClassification,
    LiveCandidateRejectionReason,
    SkinMetadataCatalog,
)
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionError,
    LiveRecipeConstructionResult,
    construct_live_recipes,
)
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeSolverConfig,
)
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
)
from app.services.steamapis_offer_pool import SteamApisOfferPool

BASE_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
POOL_NOW = BASE_TIME + timedelta(minutes=5)
PURCHASE_BASE = "https://example.invalid/manual/live-recipe"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "live_recipe_construction.py"
)


def _observation(
    *,
    index: int,
    market_hash_name: str,
    price_cny: str,
    float_value: str,
    paint_seed: int,
    link_group: str = "eligible",
) -> SteamApisListingObservation:
    purchase_link = f"{PURCHASE_BASE}/{link_group}/{index}"
    return SteamApisListingObservation(
        source_offer_id=make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            purchase_link,
        ),
        event_type=SteamApisListingEventType.ADDED,
        marketplace="Buff163",
        game="CS2",
        market_hash_name=market_hash_name,
        purchase_link=purchase_link,
        inspect_link=f"steam://inspect/live-recipe-{index}",
        price_cny=Decimal(price_cny),
        float_value=Decimal(float_value),
        paint_index=100 + index,
        paint_seed=paint_seed,
        days_trade_locked=None,
        found_at=BASE_TIME - timedelta(minutes=1),
        message_timestamp=BASE_TIME,
        stickers=(),
    )


def _skin(
    *,
    market_hash_name: str,
    rarity: str,
    collection_name: str,
    stattrak: bool = False,
    souvenir: bool = False,
) -> SkinMetadata:
    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=market_hash_name,
        weapon="Synthetic Weapon",
        rarity=rarity,
        category="Rifle",
        collection_name=collection_name,
        min_float=0.0,
        max_float=1.0,
        stattrak=stattrak,
        souvenir=souvenir,
        raw={"sensitive": "discard-me"},
    )


def _config(
    *,
    stattrak: bool | None = False,
    souvenir: bool | None = False,
) -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity="Restricted",
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        max_candidates_per_collection=None,
        target_stattrak=stattrak,
        target_souvenir=souvenir,
    )


def _base_skins() -> list[SkinMetadata]:
    return [
        _skin(
            market_hash_name="Alpha Input",
            rarity="Restricted",
            collection_name="Collection Alpha",
        ),
        _skin(
            market_hash_name="Beta Input",
            rarity="Restricted",
            collection_name="Collection Beta",
        ),
        _skin(
            market_hash_name="Alpha Output",
            rarity="Classified",
            collection_name="Collection Alpha",
        ),
        _skin(
            market_hash_name="Beta Output",
            rarity="Classified",
            collection_name="Collection Beta",
        ),
    ]


def _base_observations() -> list[SteamApisListingObservation]:
    observations = [
        _observation(
            index=0,
            market_hash_name="Alpha Input",
            price_cny="10.00",
            float_value="0.10",
            paint_seed=777,
        ),
        _observation(
            index=1,
            market_hash_name="Alpha Input",
            price_cny="10.00",
            float_value="0.10",
            paint_seed=777,
        ),
    ]
    observations.extend(
        _observation(
            index=index,
            market_hash_name=("Alpha Input" if index < 6 else "Beta Input"),
            price_cny=f"{10 + index}.00",
            float_value=f"0.{10 + index}",
            paint_seed=700 + index,
        )
        for index in range(2, 11)
    )
    observations.append(
        _observation(
            index=99,
            market_hash_name="Unknown Input",
            price_cny="1.00",
            float_value="0.01",
            paint_seed=999,
            link_group="rejected",
        )
    )
    return observations


def _pool_with(
    observations: list[SteamApisListingObservation],
) -> SteamApisOfferPool:
    pool = SteamApisOfferPool(
        max_size=100,
        ttl=timedelta(hours=1),
        now=lambda: POOL_NOW,
    )
    for observation in observations:
        pool.ingest(observation)
    return pool


def _base_context() -> tuple[SteamApisOfferPool, SkinMetadataCatalog]:
    return _pool_with(_base_observations()), SkinMetadataCatalog(skins=_base_skins())


def _construct_base() -> tuple[
    SteamApisOfferPool,
    SkinMetadataCatalog,
    LiveRecipeConstructionResult,
]:
    pool, catalog = _base_context()
    result = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=catalog,
        solver_config=_config(),
    )
    return pool, catalog, result


def test_public_api_signatures_and_dto_contracts_are_exact() -> None:
    assert construction_module.__all__ == (
        "LiveRecipeConstructionError",
        "LiveConstructedRecipe",
        "LiveRecipeConstructionResult",
        "construct_live_recipes",
    )
    assert [field.name for field in fields(LiveConstructedRecipe)] == [
        "recipe",
        "selected_source_offer_ids",
    ]
    assert [field.name for field in fields(LiveRecipeConstructionResult)] == [
        "classification",
        "recipes",
    ]
    parameters = list(signature(construct_live_recipes).parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "snapshot",
        "catalog",
        "solver_config",
    ]
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for parameter in parameters)
    assert get_type_hints(construct_live_recipes)["return"] is (
        LiveRecipeConstructionResult
    )


def test_live_result_is_frozen_tuple_backed_and_repr_safe() -> None:
    pool, _, result = _construct_base()
    recipe = result.recipes[0]
    selected_link = pool.get_purchase_link(recipe.selected_source_offer_ids[0])

    assert type(result.recipes) is tuple
    assert type(recipe.selected_source_offer_ids) is tuple
    assert type(recipe.recipe) is ConstructedRecipe
    rendered_result = repr(result)
    rendered_recipe = repr(recipe)
    assert "LiveRecipeConstructionResult object" in rendered_result
    assert "LiveConstructedRecipe object" in rendered_recipe
    assert "selected_source_offer_ids" not in rendered_result
    assert "selected_source_offer_ids" not in rendered_recipe
    assert selected_link is not None
    assert selected_link not in rendered_result
    with pytest.raises(TypeError):
        LiveConstructedRecipe(  # type: ignore[misc]
            recipe.recipe,
            recipe.selected_source_offer_ids,
        )
    with pytest.raises(FrozenInstanceError):
        result.recipes = ()  # type: ignore[misc]


def test_synthetic_snapshot_constructs_one_real_multi_collection_recipe() -> None:
    _, _, result = _construct_base()

    assert len(result.classification.eligible) == 11
    assert len(result.classification.rejected) == 1
    assert result.classification.rejected[0].reason_code is (
        LiveCandidateRejectionReason.METADATA_NOT_FOUND
    )
    assert len(result.classification.buckets) == 1
    assert result.classification.buckets[0].affected_collections == frozenset(
        {"Collection Alpha", "Collection Beta"}
    )
    assert len(result.recipes) == 1

    live_recipe = result.recipes[0]
    recipe = live_recipe.recipe
    assert len(recipe.input_items) == 10
    assert {item.collection_name for item in recipe.input_items} == {
        "Collection Alpha",
        "Collection Beta",
    }
    assert recipe.tradeup_results
    assert sum(output.probability for output in recipe.tradeup_results) == pytest.approx(
        1.0
    )
    assert recipe.input_total_cost_cny == sum(
        (item.price_cny for item in recipe.input_items),
        start=Decimal("0"),
    )
    assert len(recipe.paint_seeds) == 10
    assert len(live_recipe.selected_source_offer_ids) == 10
    assert len(set(live_recipe.selected_source_offer_ids)) == 10


def test_selected_source_ids_follow_exact_solver_listing_order() -> None:
    _, _, result = _construct_base()
    bucket = result.classification.buckets[0]
    expected_bindings = sorted(
        bucket.bindings,
        key=lambda binding: (
            binding.candidate.float_value,
            binding.candidate.price_cny,
            binding.candidate.market_hash_name,
            binding.candidate.listing_id,
        ),
    )[:10]

    assert result.recipes[0].selected_source_offer_ids == tuple(
        binding.source_offer_id for binding in expected_bindings
    )
    assert result.recipes[0].recipe.paint_seeds == tuple(
        binding.candidate.paint_seed
        for binding in expected_bindings
        if binding.candidate.paint_seed is not None
    )


def test_identical_economics_listings_remain_exactly_distinguishable() -> None:
    _, _, result = _construct_base()
    identical_ids = {
        observation.source_offer_id
        for observation in _base_observations()[:2]
    }
    selected_ids = result.recipes[0].selected_source_offer_ids

    assert len(identical_ids) == 2
    assert identical_ids.issubset(selected_ids)
    selected_identical = [
        binding
        for binding in result.classification.eligible
        if binding.source_offer_id in identical_ids
    ]
    assert len(selected_identical) == 2
    assert len({binding.candidate.listing_id for binding in selected_identical}) == 2
    assert {
        (
            binding.candidate.market_hash_name,
            binding.candidate.price_cny,
            binding.candidate.float_value,
            binding.candidate.paint_seed,
        )
        for binding in selected_identical
    } == {("Alpha Input", Decimal("10.00"), 0.10, 777)}


def test_every_selected_source_id_joins_back_to_pool_purchase_provenance() -> None:
    pool, _, result = _construct_base()

    for source_offer_id in result.recipes[0].selected_source_offer_ids:
        observation = pool.get_observation(source_offer_id)
        purchase_link = pool.get_purchase_link(source_offer_id)
        assert observation is not None
        assert observation.source_offer_id == source_offer_id
        assert purchase_link == observation.purchase_link
        assert purchase_link
        assert purchase_link not in repr(result)


def test_fewer_than_ten_eligible_candidates_returns_no_recipe() -> None:
    observations = _base_observations()[:9]
    pool = _pool_with(observations)
    result = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=SkinMetadataCatalog(skins=_base_skins()),
        solver_config=_config(),
    )

    assert len(result.classification.eligible) == 9
    assert result.recipes == ()


def test_rejected_observations_never_enter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog = _base_context()
    captured_candidates: list[object] = []
    original = construction_module.construct_recipe_selections

    def construct(candidates: list[object], *args: object) -> object:
        captured_candidates.extend(candidates)
        return original(candidates, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(construction_module, "construct_recipe_selections", construct)
    result = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=catalog,
        solver_config=_config(),
    )

    rejected_id = result.classification.rejected[0].source_offer_id
    assert len(captured_candidates) == 11
    assert all(
        candidate.listing_id != f"steamapis:buff163:{rejected_id}"
        for candidate in captured_candidates
    )


def test_classification_runs_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog = _base_context()
    original = construction_module.classify_steamapis_snapshot
    calls = 0

    def classify(*args: object) -> LiveCandidateClassification:
        nonlocal calls
        calls += 1
        return original(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(construction_module, "classify_steamapis_snapshot", classify)

    result = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=catalog,
        solver_config=_config(),
    )

    assert len(result.recipes) == 1
    assert calls == 1


def test_none_targets_process_exact_mode_buckets_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal_observations = _base_observations()[:10]
    stattrak_observations = [
        _observation(
            index=100 + index,
            market_hash_name="StatTrak Input",
            price_cny=f"{30 + index}.00",
            float_value=f"0.{20 + index}",
            paint_seed=1000 + index,
            link_group="stattrak",
        )
        for index in range(10)
    ]
    skins = [
        *_base_skins(),
        _skin(
            market_hash_name="StatTrak Input",
            rarity="Restricted",
            collection_name="Collection StatTrak",
            stattrak=True,
        ),
        _skin(
            market_hash_name="StatTrak Output",
            rarity="Classified",
            collection_name="Collection StatTrak",
            stattrak=True,
        ),
    ]
    pool = _pool_with([*normal_observations, *stattrak_observations])
    calls: list[tuple[bool | None, tuple[bool, ...]]] = []
    original = construction_module.construct_recipe_selections

    def construct(
        candidates: list[object],
        metadata: list[SkinMetadata],
        config: RecipeSolverConfig,
    ) -> object:
        input_modes = tuple(
            sorted(
                {
                    skin.stattrak
                    for skin in metadata
                    if skin.rarity == config.input_rarity
                }
            )
        )
        calls.append((config.target_stattrak, input_modes))
        return original(candidates, metadata, config)  # type: ignore[arg-type]

    monkeypatch.setattr(construction_module, "construct_recipe_selections", construct)
    result = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=SkinMetadataCatalog(skins=skins),
        solver_config=_config(stattrak=None),
    )

    assert len(result.recipes) == 2
    assert calls == [(False, (False,)), (True, (True,))]
    assert [recipe.recipe.input_items[0].stattrak for recipe in result.recipes] == [
        False,
        True,
    ]


def test_explicit_mode_target_excludes_other_bucket() -> None:
    normal_observations = _base_observations()[:10]
    stattrak_observations = [
        _observation(
            index=200 + index,
            market_hash_name="StatTrak Input",
            price_cny=f"{30 + index}.00",
            float_value=f"0.{20 + index}",
            paint_seed=2000 + index,
            link_group="stattrak-explicit",
        )
        for index in range(10)
    ]
    skins = [
        *_base_skins(),
        _skin(
            market_hash_name="StatTrak Input",
            rarity="Restricted",
            collection_name="Collection StatTrak",
            stattrak=True,
        ),
        _skin(
            market_hash_name="StatTrak Output",
            rarity="Classified",
            collection_name="Collection StatTrak",
            stattrak=True,
        ),
    ]
    result = construct_live_recipes(
        snapshot=_pool_with(
            [*normal_observations, *stattrak_observations]
        ).snapshot(),
        catalog=SkinMetadataCatalog(skins=skins),
        solver_config=_config(stattrak=True),
    )

    assert len(result.recipes) == 1
    assert all(item.stattrak for item in result.recipes[0].recipe.input_items)


def test_repeated_construction_is_deterministic_without_mutation() -> None:
    pool, catalog = _base_context()
    snapshot = pool.snapshot()
    config = _config()

    first = construct_live_recipes(
        snapshot=snapshot,
        catalog=catalog,
        solver_config=config,
    )
    second = construct_live_recipes(
        snapshot=snapshot,
        catalog=catalog,
        solver_config=config,
    )

    assert first == second
    assert first is not second
    assert first.recipes[0] is not second.recipes[0]
    assert pool.snapshot() == snapshot
    assert config == _config()


@pytest.mark.parametrize(
    "identity_case",
    ["unknown", "duplicate", "partial", "cross-bucket", "reordered"],
)
def test_invalid_selected_listing_provenance_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    identity_case: str,
) -> None:
    pool, catalog = _base_context()
    original = construction_module.construct_recipe_selections

    def construct(*args: object) -> list[ConstructedRecipeSelection]:
        valid = original(*args)  # type: ignore[arg-type]
        selection = valid[0]
        listing_ids = selection.selected_listing_ids
        if identity_case == "unknown":
            listing_ids = ("unknown-listing", *listing_ids[1:])
        elif identity_case == "duplicate":
            listing_ids = (listing_ids[0], listing_ids[0], *listing_ids[2:])
        elif identity_case == "partial":
            listing_ids = listing_ids[:-1]
        elif identity_case == "cross-bucket":
            rejected_id = make_steamapis_source_offer_id(
                "Buff163",
                "CS2",
                f"{PURCHASE_BASE}/rejected/99",
            )
            listing_ids = (
                f"steamapis:buff163:{rejected_id}",
                *listing_ids[1:],
            )
        else:
            listing_ids = tuple(reversed(listing_ids))
        return [
            ConstructedRecipeSelection(
                recipe=selection.recipe,
                selected_listing_ids=listing_ids,
            )
        ]

    monkeypatch.setattr(construction_module, "construct_recipe_selections", construct)

    with pytest.raises(LiveRecipeConstructionError) as exc_info:
        construct_live_recipes(
            snapshot=pool.snapshot(),
            catalog=catalog,
            solver_config=_config(),
        )

    assert str(exc_info.value) == "invalid live recipe construction contract"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_late_invalid_selection_returns_no_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog = _base_context()
    original = construction_module.construct_recipe_selections

    def construct(*args: object) -> list[ConstructedRecipeSelection]:
        valid = original(*args)  # type: ignore[arg-type]
        return [
            valid[0],
            ConstructedRecipeSelection(
                recipe=valid[0].recipe,
                selected_listing_ids=(
                    "unknown-listing",
                    *valid[0].selected_listing_ids[1:],
                ),
            ),
        ]

    monkeypatch.setattr(construction_module, "construct_recipe_selections", construct)

    with pytest.raises(LiveRecipeConstructionError):
        construct_live_recipes(
            snapshot=pool.snapshot(),
            catalog=catalog,
            solver_config=_config(),
        )


def test_empty_all_rejected_unmatched_and_terminal_inputs_return_no_recipes() -> None:
    catalog = SkinMetadataCatalog(skins=_base_skins())
    empty_pool = _pool_with([])
    assert construct_live_recipes(
        snapshot=empty_pool.snapshot(),
        catalog=catalog,
        solver_config=_config(),
    ).recipes == ()

    rejected_pool = _pool_with([_base_observations()[-1]])
    rejected = construct_live_recipes(
        snapshot=rejected_pool.snapshot(),
        catalog=catalog,
        solver_config=_config(),
    )
    assert len(rejected.classification.rejected) == 1
    assert rejected.recipes == ()

    pool, _ = _base_context()
    unmatched = construct_live_recipes(
        snapshot=pool.snapshot(),
        catalog=catalog,
        solver_config=replace(_config(), input_rarity="Mil-Spec Grade"),
    )
    assert unmatched.recipes == ()

    covert_catalog = SkinMetadataCatalog(
        skins=[
            _skin(
                market_hash_name="Covert Input",
                rarity="Covert",
                collection_name="Covert Collection",
            )
        ]
    )
    covert_pool = _pool_with(
        [
            _observation(
                index=300 + index,
                market_hash_name="Covert Input",
                price_cny="10.00",
                float_value="0.10",
                paint_seed=index,
                link_group="covert",
            )
            for index in range(10)
        ]
    )
    terminal = construct_live_recipes(
        snapshot=covert_pool.snapshot(),
        catalog=covert_catalog,
        solver_config=replace(_config(), input_rarity="Covert"),
    )
    assert len(terminal.classification.eligible) == 10
    assert terminal.recipes == ()


@pytest.mark.parametrize(
    "expected",
    [MemoryError(), KeyboardInterrupt(), asyncio.CancelledError()],
    ids=["memory", "keyboard-interrupt", "cancelled"],
)
def test_memory_and_control_flow_failures_propagate_by_identity(
    monkeypatch: pytest.MonkeyPatch,
    expected: BaseException,
) -> None:
    pool, catalog = _base_context()

    def fail(*args: object) -> None:
        raise expected

    monkeypatch.setattr(construction_module, "classify_steamapis_snapshot", fail)

    with pytest.raises(type(expected)) as exc_info:
        construct_live_recipes(
            snapshot=pool.snapshot(),
            catalog=catalog,
            solver_config=_config(),
        )

    assert exc_info.value is expected


def test_ordinary_collaborator_failure_is_fixed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog = _base_context()
    sensitive = f"Cookie=dummy-cookie {PURCHASE_BASE} Alpha Input"

    def fail(*args: object) -> None:
        raise RuntimeError(sensitive)

    monkeypatch.setattr(construction_module, "construct_recipe_selections", fail)

    with pytest.raises(LiveRecipeConstructionError) as exc_info:
        construct_live_recipes(
            snapshot=pool.snapshot(),
            catalog=catalog,
            solver_config=_config(),
        )

    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert rendered == (
        "invalid live recipe construction contract "
        "LiveRecipeConstructionError('invalid live recipe construction contract')"
    )
    assert sensitive not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_module_has_exact_offline_construction_import_boundary() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    direct_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported_modules == {
        "__future__",
        "dataclasses",
        "decimal",
        "app.services.live_metadata_catalog",
        "app.services.metadata_service",
        "app.services.recipe_solver",
        "app.services.steamapis_offer_pool",
        "app.services.tradeup_engine",
    }
    assert direct_imports == {"math"}


def test_module_contains_no_evaluation_external_or_background_behavior() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_names = {
        "solve_recipes",
        "calculate_opportunity_metrics",
        "evaluate_opportunity",
        "ValuationService",
        "SteamDTPriceProvider",
        "SteamDTHttpClient",
        "Redis",
        "BuffClient",
        "httpx",
        "websockets",
        "WebSocket",
        "create_task",
        "TaskGroup",
        "Thread",
        "Scheduler",
        "getenv",
        "environ",
        "purchase_link",
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert forbidden_names.isdisjoint(referenced_names | referenced_attributes)
    assert "steamapis:buff163:" not in source
    assert "split(" not in source
    assert "startswith(" not in source
    assert "http://" not in source
    assert "https://" not in source
