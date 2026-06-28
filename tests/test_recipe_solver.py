from datetime import UTC
from decimal import Decimal

import pytest

from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    RecipeCandidate,
    RecipeSolverConfig,
    build_recipe_hash,
    solve_recipes,
)
from app.services.risk_filter import RiskFilterConfig


def _make_candidate(
    *,
    market_hash_name: str | None = "AK-47 | Redline (Field-Tested)",
    listing_id: str = "listing-1",
    price_cny: str = "10.00",
    float_value: float | None = 0.10,
) -> CandidateListing:
    return CandidateListing(
        goods_id="goods-1",
        listing_id=listing_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal(price_cny),
        float_value=float_value,
        paint_seed=123,
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
