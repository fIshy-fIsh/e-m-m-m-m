import asyncio
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC
from decimal import Decimal
from inspect import Parameter, signature

import pytest

import app.services.recipe_solver as recipe_solver_module
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeCandidate,
    RecipeSolverConfig,
    build_recipe_hash,
    construct_recipe_selections,
    construct_recipes,
    solve_recipes,
)
from app.services.risk_filter import RiskFilterConfig
from app.services.tradeup_engine import InputItem, TradeupResult


def _make_candidate(
    *,
    market_hash_name: str | None = "AK-47 | Redline (Field-Tested)",
    listing_id: str = "listing-1",
    price_cny: str = "10.00",
    float_value: float | None = 0.10,
    paint_seed: int | None = 123,
) -> CandidateListing:
    return CandidateListing(
        goods_id="goods-1",
        listing_id=listing_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal(price_cny),
        float_value=float_value,
        paint_seed=paint_seed,
        inspect_link="steam://inspect/test",
        scanned_at=__import__("datetime").datetime.now(UTC),
        raw={"listing_id": listing_id},
    )



def _make_skin(
    *,
    market_hash_name: str,
    rarity: str = "Restricted",
    collection_name: str | None = "Collection Alpha",
    min_float: float = 0.00,
    max_float: float = 1.00,
    stattrak: bool = False,
    souvenir: bool = False,
) -> SkinMetadata:
    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=market_hash_name,
        weapon="AK-47",
        rarity=rarity,
        category="Rifle",
        collection_name=collection_name,
        min_float=min_float,
        max_float=max_float,
        stattrak=stattrak,
        souvenir=souvenir,
        raw={"market_hash_name": market_hash_name},
    )



def _make_solver_config(**overrides: object) -> RecipeSolverConfig:
    base = {
        "input_rarity": "Restricted",
        "input_count": 10,
        "sell_fee_rate": Decimal("0.025"),
        "max_candidates_per_collection": None,
        "target_stattrak": None,
        "target_souvenir": None,
    }
    base.update(overrides)
    return RecipeSolverConfig(**base)



def _make_risk_config() -> RiskFilterConfig:
    return RiskFilterConfig(
        min_roi=Decimal("0.05"),
        min_expected_profit_cny=Decimal("20.00"),
        max_worst_case_loss_pct=Decimal("0.25"),
        min_profit_probability=0.35,
        max_input_total_cost_cny=Decimal("1000.00"),
    )



def _build_basic_recipe_inputs() -> tuple[list[CandidateListing], list[SkinMetadata]]:
    candidates = [
        _make_candidate(
            market_hash_name=f"Input Skin {index}",
            listing_id=f"listing-{index}",
            price_cny=f"{10 + index}.00",
            float_value=0.10 + index * 0.01,
        )
        for index in range(10)
    ]
    skins = [
        _make_skin(
            market_hash_name=f"Input Skin {index}",
            rarity="Restricted",
            collection_name="Collection Alpha",
            min_float=0.00,
            max_float=1.00,
        )
        for index in range(10)
    ] + [
        _make_skin(
            market_hash_name="Output Skin A",
            rarity="Classified",
            collection_name="Collection Alpha",
            min_float=0.00,
            max_float=0.80,
        )
    ]
    return candidates, skins



def _build_basic_construction() -> ConstructedRecipe:
    candidates, skins = _build_basic_recipe_inputs()
    constructions = construct_recipes(candidates, skins, _make_solver_config())
    return constructions[0]



def test_recipe_solver_public_signatures_remain_exact() -> None:
    construction_parameters = list(signature(construct_recipes).parameters.values())
    assert [parameter.name for parameter in construction_parameters] == [
        "candidates",
        "skins",
        "solver_config",
    ]
    assert all(
        parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        for parameter in construction_parameters
    )
    assert all(
        parameter.default is Parameter.empty
        for parameter in construction_parameters
    )
    assert signature(construct_recipes).return_annotation == list[ConstructedRecipe]

    selection_parameters = list(
        signature(construct_recipe_selections).parameters.values()
    )
    assert [parameter.name for parameter in selection_parameters] == [
        "candidates",
        "skins",
        "solver_config",
    ]
    assert all(
        parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        for parameter in selection_parameters
    )
    assert all(
        parameter.default is Parameter.empty for parameter in selection_parameters
    )
    assert signature(construct_recipe_selections).return_annotation == list[
        ConstructedRecipeSelection
    ]

    solve_parameters = list(signature(solve_recipes).parameters.values())
    assert [parameter.name for parameter in solve_parameters] == [
        "candidates",
        "skins",
        "solver_config",
        "risk_config",
        "liquidity_score",
    ]
    assert all(
        parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        for parameter in solve_parameters
    )
    assert [parameter.default for parameter in solve_parameters] == [
        Parameter.empty,
        Parameter.empty,
        Parameter.empty,
        Parameter.empty,
        None,
    ]
    assert signature(solve_recipes).return_annotation == list[RecipeCandidate]



def test_constructed_recipe_has_strict_immutable_contract() -> None:
    construction = _build_basic_construction()

    assert [field.name for field in fields(construction)] == [
        "input_items",
        "tradeup_results",
        "paint_seeds",
    ]
    assert type(construction.input_items) is tuple
    assert type(construction.tradeup_results) is tuple
    assert type(construction.paint_seeds) is tuple
    assert all(type(item) is InputItem for item in construction.input_items)
    assert all(
        type(result) is TradeupResult for result in construction.tradeup_results
    )
    assert construction.input_total_cost_cny == Decimal("145.00")
    assert "Input Skin" not in repr(construction)
    assert "145.00" not in repr(construction)
    with pytest.raises(FrozenInstanceError):
        construction.paint_seeds = ()  # type: ignore[misc]



def test_constructed_recipe_is_keyword_only() -> None:
    construction = _build_basic_construction()

    with pytest.raises(TypeError):
        ConstructedRecipe(  # type: ignore[misc]
            construction.input_items,
            construction.tradeup_results,
            construction.paint_seeds,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("input_items", [], "input_items"),
        ("input_items", (), "exactly 10"),
        ("tradeup_results", [], "tradeup_results"),
        ("tradeup_results", (), "cannot be empty"),
        ("paint_seeds", [], "paint_seeds"),
        ("paint_seeds", (True,), "paint_seeds"),
    ],
)
def test_constructed_recipe_rejects_invalid_state(
    field_name: str,
    invalid_value: object,
    message: str,
) -> None:
    construction = _build_basic_construction()
    values = {
        "input_items": construction.input_items,
        "tradeup_results": construction.tradeup_results,
        "paint_seeds": construction.paint_seeds,
    }
    values[field_name] = invalid_value

    with pytest.raises((TypeError, ValueError), match=message):
        ConstructedRecipe(**values)  # type: ignore[arg-type]


def test_constructed_recipe_selection_has_strict_identity_contract() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    selection = construct_recipe_selections(
        candidates,
        skins,
        _make_solver_config(),
    )[0]

    assert [field.name for field in fields(selection)] == [
        "recipe",
        "selected_listing_ids",
    ]
    assert type(selection.recipe) is ConstructedRecipe
    assert selection.selected_listing_ids == tuple(
        f"listing-{index}" for index in range(10)
    )
    assert type(selection.selected_listing_ids) is tuple
    assert "listing-0" not in repr(selection)
    with pytest.raises(TypeError):
        ConstructedRecipeSelection(  # type: ignore[misc]
            selection.recipe,
            selection.selected_listing_ids,
        )
    with pytest.raises(FrozenInstanceError):
        selection.selected_listing_ids = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "listing_ids",
    [[], (), tuple("" for _ in range(10)), tuple("id" for _ in range(9))],
)
def test_constructed_recipe_selection_rejects_invalid_listing_identity(
    listing_ids: object,
) -> None:
    construction = _build_basic_construction()

    with pytest.raises((TypeError, ValueError), match="selected_listing_ids"):
        ConstructedRecipeSelection(
            recipe=construction,
            selected_listing_ids=listing_ids,  # type: ignore[arg-type]
        )


def test_construct_recipe_selections_distinguishes_identical_economics() -> None:
    candidates = [
        _make_candidate(
            market_hash_name="Shared Input",
            listing_id=f"listing-{index:02d}",
            price_cny="10.00",
            float_value=0.10,
            paint_seed=123,
        )
        for index in reversed(range(11))
    ]
    skins = [
        _make_skin(market_hash_name="Shared Input"),
        _make_skin(
            market_hash_name="Output Skin A",
            rarity="Classified",
            collection_name="Collection Alpha",
        ),
    ]

    selection = construct_recipe_selections(
        candidates,
        skins,
        _make_solver_config(),
    )[0]

    assert selection.selected_listing_ids == tuple(
        f"listing-{index:02d}" for index in range(10)
    )
    assert len(set(selection.selected_listing_ids)) == 10
    assert all(item.actual_float == 0.10 for item in selection.recipe.input_items)
    assert all(item.price_cny == Decimal("10.00") for item in selection.recipe.input_items)
    assert selection.recipe.paint_seeds == (123,) * 10


def test_construct_recipes_preserves_str_subclass_listing_id_compatibility() -> None:
    class ListingId(str):
        pass

    candidates, skins = _build_basic_recipe_inputs()
    candidates = [
        replace(candidate, listing_id=ListingId(candidate.listing_id))
        for candidate in candidates
    ]

    selections = construct_recipe_selections(
        candidates,
        skins,
        _make_solver_config(),
    )
    constructions = construct_recipes(candidates, skins, _make_solver_config())

    assert len(selections) == 1
    assert all(type(listing_id) is str for listing_id in selections[0].selected_listing_ids)
    assert constructions == [selections[0].recipe]


def test_construct_recipes_projects_authoritative_selection_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    expected = construct_recipe_selections(candidates, skins, _make_solver_config())
    calls: list[tuple[object, ...]] = []

    def select(
        received_candidates: list[CandidateListing],
        received_skins: list[SkinMetadata],
        received_config: RecipeSolverConfig,
    ) -> list[ConstructedRecipeSelection]:
        calls.append((received_candidates, received_skins, received_config))
        return expected

    monkeypatch.setattr(recipe_solver_module, "construct_recipe_selections", select)
    config = _make_solver_config()

    assert construct_recipes(candidates, skins, config) == [
        selection.recipe for selection in expected
    ]
    assert calls == [(candidates, skins, config)]


def test_construct_recipe_selections_calculates_tradeup_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    original = recipe_solver_module.calculate_tradeup_results
    calls = 0

    def calculate(
        input_items: list[InputItem],
        outputs: dict[str, list[object]],
    ) -> list[TradeupResult]:
        nonlocal calls
        calls += 1
        return original(input_items, outputs)  # type: ignore[arg-type]

    monkeypatch.setattr(recipe_solver_module, "calculate_tradeup_results", calculate)

    selections = construct_recipe_selections(
        candidates,
        skins,
        _make_solver_config(),
    )

    assert len(selections) == 1
    assert calls == 1



def test_construct_recipes_builds_one_ordered_recipe() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    constructions = construct_recipes(candidates, skins, _make_solver_config())

    assert len(constructions) == 1
    construction = constructions[0]
    assert type(construction) is ConstructedRecipe
    assert [item.market_hash_name for item in construction.input_items] == [
        f"Input Skin {index}" for index in range(10)
    ]
    assert len(construction.input_items) == 10
    assert [result.output_market_hash_name for result in construction.tradeup_results] == [
        "Output Skin A"
    ]



def test_construct_recipes_does_not_execute_ev_or_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("opportunity evaluation must not run")

    monkeypatch.setattr(recipe_solver_module, "calculate_opportunity_metrics", fail)
    monkeypatch.setattr(recipe_solver_module, "evaluate_opportunity", fail)

    constructions = construct_recipes(candidates, skins, _make_solver_config())

    assert len(constructions) == 1



def test_construct_recipes_preserves_compact_ordered_paint_seeds() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    seeds = [0, None, 20, 30, None, 50, 60, 70, 80, 90]
    for index, seed in enumerate(seeds):
        candidates[index] = _make_candidate(
            market_hash_name=f"Input Skin {index}",
            listing_id=f"listing-{index}",
            price_cny=f"{10 + index}.00",
            float_value=0.10 + index * 0.01,
            paint_seed=seed,
        )

    construction = construct_recipes(
        candidates,
        skins,
        _make_solver_config(),
    )[0]

    assert construction.paint_seeds == (0, 20, 30, 50, 60, 70, 80, 90)



def test_construct_recipes_is_deterministic_without_mutating_inputs() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    original_candidates = list(candidates)
    original_skins = list(skins)

    first = construct_recipes(candidates, skins, _make_solver_config())
    second = construct_recipes(candidates, skins, _make_solver_config())

    assert first == second
    assert first is not second
    assert first[0] is not second[0]
    assert candidates == original_candidates
    assert skins == original_skins



def test_construct_recipes_uses_listing_id_as_final_selection_tiebreaker() -> None:
    candidates = [
        _make_candidate(
            market_hash_name="Shared Input",
            listing_id=f"listing-{index:02d}",
            price_cny="10.00",
            float_value=0.10,
            paint_seed=index,
        )
        for index in reversed(range(11))
    ]
    skins = [
        _make_skin(market_hash_name="Shared Input"),
        _make_skin(
            market_hash_name="Output Skin A",
            rarity="Classified",
            collection_name="Collection Alpha",
        ),
    ]

    construction = construct_recipes(
        candidates,
        skins,
        _make_solver_config(),
    )[0]

    assert construction.paint_seeds == tuple(range(10))



def test_construct_recipes_returns_empty_for_tradeup_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()

    def fail(*args: object, **kwargs: object) -> list[TradeupResult]:
        raise ValueError("invalid trade-up")

    monkeypatch.setattr(recipe_solver_module, "calculate_tradeup_results", fail)

    assert construct_recipes(candidates, skins, _make_solver_config()) == []


@pytest.mark.parametrize(
    "expected",
    [MemoryError(), KeyboardInterrupt(), asyncio.CancelledError()],
    ids=["memory", "keyboard-interrupt", "cancelled"],
)
def test_construct_recipes_propagates_control_flow_identity(
    monkeypatch: pytest.MonkeyPatch,
    expected: BaseException,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()

    def fail(*args: object, **kwargs: object) -> list[TradeupResult]:
        raise expected

    monkeypatch.setattr(recipe_solver_module, "calculate_tradeup_results", fail)

    with pytest.raises(type(expected)) as exc_info:
        construct_recipes(candidates, skins, _make_solver_config())

    assert exc_info.value is expected



def test_construct_recipes_propagates_unexpected_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    expected = RuntimeError("engine failed")

    def fail(*args: object, **kwargs: object) -> list[TradeupResult]:
        raise expected

    monkeypatch.setattr(recipe_solver_module, "calculate_tradeup_results", fail)

    with pytest.raises(RuntimeError) as exc_info:
        construct_recipes(candidates, skins, _make_solver_config())

    assert exc_info.value is expected



def test_construct_recipes_propagates_output_pool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    expected = ValueError("unsupported rarity")

    def fail(*args: object, **kwargs: object) -> object:
        raise expected

    monkeypatch.setattr(
        recipe_solver_module,
        "build_output_candidates_by_collection",
        fail,
    )

    with pytest.raises(ValueError) as exc_info:
        construct_recipes(candidates, skins, _make_solver_config())

    assert exc_info.value is expected



def test_solve_recipes_delegates_once_and_does_not_repeat_tradeup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    config = _make_solver_config()
    calls: list[tuple[object, ...]] = []
    construction = _build_basic_construction()

    def construct(
        received_candidates: list[CandidateListing],
        received_skins: list[SkinMetadata],
        received_config: RecipeSolverConfig,
    ) -> list[ConstructedRecipe]:
        calls.append((received_candidates, received_skins, received_config))
        return [construction]

    def fail_tradeup(*args: object, **kwargs: object) -> None:
        raise AssertionError("trade-up engine must not run during evaluation")

    monkeypatch.setattr(recipe_solver_module, "construct_recipes", construct)
    monkeypatch.setattr(
        recipe_solver_module,
        "calculate_tradeup_results",
        fail_tradeup,
    )

    recipes = solve_recipes(candidates, skins, config, _make_risk_config())

    assert calls == [(candidates, skins, config)]
    assert len(recipes) == 1



def test_solve_recipes_short_circuits_evaluation_for_no_constructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()

    monkeypatch.setattr(recipe_solver_module, "construct_recipes", lambda *_args: [])

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("evaluation must not run")

    monkeypatch.setattr(recipe_solver_module, "calculate_opportunity_metrics", fail)
    monkeypatch.setattr(recipe_solver_module, "evaluate_opportunity", fail)

    assert solve_recipes(
        candidates,
        skins,
        _make_solver_config(),
        _make_risk_config(),
    ) == []



def test_solve_recipes_evaluates_each_construction_once_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    first = _build_basic_construction()
    second_items = (
        replace(first.input_items[0], market_hash_name="Second Recipe Input"),
        *first.input_items[1:],
    )
    second = ConstructedRecipe(
        input_items=second_items,
        tradeup_results=first.tradeup_results,
        paint_seeds=tuple(reversed(first.paint_seeds)),
    )
    config = _make_solver_config()
    risk_config = _make_risk_config()
    liquidity_score = Decimal("0.75")
    events: list[str] = []
    original_metrics = recipe_solver_module.calculate_opportunity_metrics
    original_risk = recipe_solver_module.evaluate_opportunity

    monkeypatch.setattr(
        recipe_solver_module,
        "construct_recipes",
        lambda *_args: [first, second],
    )

    def calculate_metrics(**kwargs: object) -> object:
        input_items = kwargs["input_items"]
        assert isinstance(input_items, list)
        events.append(f"metrics:{input_items[0].market_hash_name}")
        assert kwargs["sell_fee_rate"] == config.sell_fee_rate
        return original_metrics(**kwargs)  # type: ignore[arg-type]

    def evaluate_risk(**kwargs: object) -> object:
        input_items = kwargs["input_items"]
        assert isinstance(input_items, list)
        events.append(f"risk:{input_items[0].market_hash_name}")
        assert kwargs["config"] is risk_config
        assert kwargs["liquidity_score"] == liquidity_score
        expected_seeds = (
            first.paint_seeds
            if input_items[0].market_hash_name == "Input Skin 0"
            else second.paint_seeds
        )
        assert kwargs["paint_seeds"] == list(expected_seeds)
        return original_risk(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        recipe_solver_module,
        "calculate_opportunity_metrics",
        calculate_metrics,
    )
    monkeypatch.setattr(recipe_solver_module, "evaluate_opportunity", evaluate_risk)

    recipes = solve_recipes(
        candidates,
        skins,
        config,
        risk_config,
        liquidity_score,
    )

    assert events == [
        "metrics:Input Skin 0",
        "risk:Input Skin 0",
        "metrics:Second Recipe Input",
        "risk:Second Recipe Input",
    ]
    assert [recipe.input_items[0].market_hash_name for recipe in recipes] == [
        "Input Skin 0",
        "Second Recipe Input",
    ]
    assert all(type(recipe) is RecipeCandidate for recipe in recipes)
    assert all(type(recipe.input_items) is list for recipe in recipes)
    assert all(type(recipe.tradeup_results) is list for recipe in recipes)
    assert recipes[0].input_items is not recipes[1].input_items
    assert recipes[0].tradeup_results is not recipes[1].tradeup_results
    assert recipes[0].input_items is not first.input_items
    assert recipes[1].input_items is not second.input_items


@pytest.mark.parametrize(
    "stage",
    ["construction", "metrics", "risk"],
)
def test_solve_recipes_propagates_stage_errors(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    candidates, skins = _build_basic_recipe_inputs()
    expected = RuntimeError(f"{stage} failed")
    construction = _build_basic_construction()

    if stage == "construction":
        def fail_construction(*args: object, **kwargs: object) -> object:
            raise expected

        monkeypatch.setattr(
            recipe_solver_module,
            "construct_recipes",
            fail_construction,
        )
    else:
        monkeypatch.setattr(
            recipe_solver_module,
            "construct_recipes",
            lambda *_args: [construction],
        )

        def fail_evaluation(*args: object, **kwargs: object) -> object:
            raise expected

        monkeypatch.setattr(
            recipe_solver_module,
            (
                "calculate_opportunity_metrics"
                if stage == "metrics"
                else "evaluate_opportunity"
            ),
            fail_evaluation,
        )

    with pytest.raises(RuntimeError) as exc_info:
        solve_recipes(
            candidates,
            skins,
            _make_solver_config(),
            _make_risk_config(),
        )

    assert exc_info.value is expected



def test_solve_recipes_preserves_exact_evaluated_recipe_contract() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    recipe = solve_recipes(
        candidates,
        skins,
        _make_solver_config(),
        _make_risk_config(),
    )[0]

    assert recipe.recipe_hash == (
        "3a6e349c5c7c623b128a9e7f3e0c83cf7c505c22c531f97201f084aa273c320b"
    )
    assert recipe.metrics.input_total_cost_cny == Decimal("145.00")
    assert recipe.metrics.expected_profit_cny == Decimal("-145.0000")
    assert recipe.metrics.roi == Decimal("-1.00")
    assert recipe.risk_decision.reason_codes == [
        "ROI_BELOW_MINIMUM",
        "EXPECTED_PROFIT_BELOW_MINIMUM",
        "WORST_CASE_LOSS_TOO_HIGH",
        "PROFIT_PROBABILITY_BELOW_MINIMUM",
    ]
    assert recipe.risk_decision.risk_score == Decimal("75")
    assert recipe.created_at.tzinfo is not None



def test_recipe_solver_config_creates_successfully() -> None:
    config = _make_solver_config()

    assert config.input_count == 10



def test_recipe_solver_config_raises_when_input_rarity_empty() -> None:
    with pytest.raises(ValueError, match="input_rarity"):
        _make_solver_config(input_rarity="")



def test_recipe_solver_config_raises_when_input_count_not_ten() -> None:
    with pytest.raises(ValueError, match="input_count"):
        _make_solver_config(input_count=9)



def test_recipe_solver_config_raises_when_sell_fee_rate_negative() -> None:
    with pytest.raises(ValueError, match="sell_fee_rate"):
        _make_solver_config(sell_fee_rate=Decimal("-0.01"))



def test_recipe_solver_config_raises_when_sell_fee_rate_not_less_than_one() -> None:
    with pytest.raises(ValueError, match="sell_fee_rate"):
        _make_solver_config(sell_fee_rate=Decimal("1.00"))



def test_solve_recipes_constructs_one_ten_item_recipe() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert len(recipes) == 1
    assert len(recipes[0].input_items) == 10



def test_solve_recipes_returns_empty_when_fewer_than_ten_candidates() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    recipes = solve_recipes(candidates[:9], skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_solve_recipes_skips_candidates_with_none_market_hash_name() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    candidates[0] = _make_candidate(market_hash_name=None, listing_id="missing-name")

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_solve_recipes_skips_candidates_with_missing_skin_metadata() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    candidates[0] = _make_candidate(market_hash_name="Unknown Skin", listing_id="unknown")

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_solve_recipes_skips_candidates_with_none_float() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    candidates[0] = _make_candidate(
        market_hash_name="Input Skin 0",
        listing_id="float-none",
        float_value=None,
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_solve_recipes_skips_candidates_with_none_collection_name() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    skins[0] = _make_skin(
        market_hash_name="Input Skin 0",
        rarity="Restricted",
        collection_name=None,
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_solve_recipes_skips_candidates_when_rarity_does_not_match() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    skins[0] = _make_skin(
        market_hash_name="Input Skin 0",
        rarity="Mil-Spec Grade",
        collection_name="Collection Alpha",
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_target_stattrak_filter_is_applied() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    for index in range(10):
        skins[index] = _make_skin(
            market_hash_name=f"Input Skin {index}",
            rarity="Restricted",
            collection_name="Collection Alpha",
            stattrak=index < 10,
        )

    recipes = solve_recipes(
        candidates,
        skins,
        _make_solver_config(target_stattrak=True),
        _make_risk_config(),
    )

    assert len(recipes) == 1
    assert all(item.stattrak for item in recipes[0].input_items)



def test_target_souvenir_filter_is_applied() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    for index in range(10):
        skins[index] = _make_skin(
            market_hash_name=f"Input Skin {index}",
            rarity="Restricted",
            collection_name="Collection Alpha",
            souvenir=True,
        )

    recipes = solve_recipes(
        candidates,
        skins,
        _make_solver_config(target_souvenir=True),
        _make_risk_config(),
    )

    assert len(recipes) == 1
    assert all(item.souvenir for item in recipes[0].input_items)



def test_adjusted_float_sorting_has_priority_over_price() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    candidates[0] = _make_candidate(
        market_hash_name="Input Skin 0",
        listing_id="higher-adjusted-cheaper",
        price_cny="5.00",
        float_value=0.50,
    )
    candidates[1] = _make_candidate(
        market_hash_name="Input Skin 1",
        listing_id="lower-adjusted-pricier",
        price_cny="20.00",
        float_value=0.10,
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes[0].input_items[0].market_hash_name == "Input Skin 1"



def test_same_adjusted_float_prefers_lower_price() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    candidates[0] = _make_candidate(
        market_hash_name="Input Skin 0",
        listing_id="higher-price",
        price_cny="20.00",
        float_value=0.10,
    )
    candidates[1] = _make_candidate(
        market_hash_name="Input Skin 1",
        listing_id="lower-price",
        price_cny="10.00",
        float_value=0.10,
    )
    skins[0] = _make_skin(
        market_hash_name="Input Skin 0",
        rarity="Restricted",
        collection_name="Collection Alpha",
        min_float=0.00,
        max_float=1.00,
    )
    skins[1] = _make_skin(
        market_hash_name="Input Skin 1",
        rarity="Restricted",
        collection_name="Collection Alpha",
        min_float=0.00,
        max_float=1.00,
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes[0].input_items[0].market_hash_name == "Input Skin 1"



def test_max_candidates_per_collection_is_applied() -> None:
    candidates = [
        _make_candidate(
            market_hash_name=f"Input Skin {index}",
            listing_id=f"listing-{index}",
            price_cny=f"{10 + index}.00",
            float_value=0.10 + index * 0.01,
        )
        for index in range(20)
    ]
    skins = [
        _make_skin(
            market_hash_name=f"Input Skin {index}",
            rarity="Restricted",
            collection_name="Collection Alpha" if index < 15 else "Collection Beta",
            min_float=0.00,
            max_float=1.00,
        )
        for index in range(20)
    ] + [
        _make_skin(
            market_hash_name="Output Skin A",
            rarity="Classified",
            collection_name="Collection Alpha",
        ),
        _make_skin(
            market_hash_name="Output Skin B",
            rarity="Classified",
            collection_name="Collection Beta",
        ),
    ]

    recipes = solve_recipes(
        candidates,
        skins,
        _make_solver_config(max_candidates_per_collection=4),
        _make_risk_config(),
    )

    assert recipes == []



def test_output_candidates_build_failure_returns_empty() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    skins = [skin for skin in skins if skin.rarity != "Classified"]

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_tradeup_engine_error_returns_empty() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    for index in range(10):
        skins[index] = _make_skin(
            market_hash_name=f"Input Skin {index}",
            rarity="Restricted",
            collection_name="Collection {index}",
        )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    assert recipes == []



def test_recipe_candidate_contains_all_expected_outputs() -> None:
    candidates, skins = _build_basic_recipe_inputs()

    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    recipe = recipes[0]
    assert isinstance(recipe, RecipeCandidate)
    assert len(recipe.input_items) == 10
    assert recipe.tradeup_results
    assert recipe.metrics is not None
    assert recipe.risk_decision is not None
    assert recipe.recipe_hash
    assert recipe.created_at.tzinfo is not None



def test_recipe_hash_is_stable_for_same_input_items() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())

    first_hash = build_recipe_hash(recipes[0].input_items)
    second_hash = build_recipe_hash(recipes[0].input_items)

    assert first_hash == second_hash



def test_recipe_hash_differs_for_different_input_items() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    recipes = solve_recipes(candidates, skins, _make_solver_config(), _make_risk_config())
    different_items = list(recipes[0].input_items)
    different_items[0] = different_items[0].__class__(
        market_hash_name="Different Skin",
        collection_name=different_items[0].collection_name,
        rarity=different_items[0].rarity,
        actual_float=different_items[0].actual_float,
        min_float=different_items[0].min_float,
        max_float=different_items[0].max_float,
        price_cny=different_items[0].price_cny,
        stattrak=different_items[0].stattrak,
        souvenir=different_items[0].souvenir,
    )

    assert build_recipe_hash(recipes[0].input_items) != build_recipe_hash(different_items)



def test_risk_filter_failure_still_returns_recipe_candidate() -> None:
    candidates, skins = _build_basic_recipe_inputs()
    strict_risk_config = RiskFilterConfig(
        min_roi=Decimal("999.0"),
        min_expected_profit_cny=Decimal("9999.0"),
        max_worst_case_loss_pct=Decimal("0.01"),
        min_profit_probability=0.99,
        max_input_total_cost_cny=Decimal("1.00"),
    )

    recipes = solve_recipes(candidates, skins, _make_solver_config(), strict_risk_config)

    assert len(recipes) == 1
    assert recipes[0].risk_decision.passed is False
