from __future__ import annotations

import ast
import inspect
import math
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.recipe_solver as recipe_solver_module
import app.services.steamdt_buff_live_recipe_fixture as fixture_module
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    ConstructedRecipeSelection,
    RecipeSolverConfig,
)
from app.services.risk_filter import RiskFilterConfig
from app.services.steamdt_buff_live_recipe_fixture import (
    STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
    SteamDTBuffLiveRecipeFixture,
    SteamDTBuffLiveRecipeFixtureError,
    build_steamdt_buff_live_recipe_fixture,
    build_verified_steamdt_buff_live_recipe_fixture,
)

OUTPUT_NAME = "Fixture Output Skin"
FIXED_ERROR = "invalid SteamDT BUFF live recipe fixture contract"
COMPATIBILITY_SOURCE = "steamapis:buff163"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamdt_buff_live_recipe_fixture.py"
)


def _build(name: str = OUTPUT_NAME) -> SteamDTBuffLiveRecipeFixture:
    return build_steamdt_buff_live_recipe_fixture(output_market_hash_name=name)


def test_public_api_is_exact_and_narrow() -> None:
    assert fixture_module.__all__ == (
        "SteamDTBuffLiveRecipeFixtureError",
        "SteamDTBuffLiveRecipeFixture",
        "STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME",
        "build_steamdt_buff_live_recipe_fixture",
        "build_verified_steamdt_buff_live_recipe_fixture",
    )
    assert STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME == (
        "M4A4 | Desolate Space (Factory New)"
    )
    assert type(STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME) is str
    assert [field.name for field in fields(SteamDTBuffLiveRecipeFixture)] == [
        "construction_result",
        "solver_config",
        "risk_config",
    ]
    signature = inspect.signature(build_steamdt_buff_live_recipe_fixture)
    assert list(signature.parameters) == ["output_market_hash_name"]
    assert (
        signature.parameters["output_market_hash_name"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["output_market_hash_name"].default is (
        inspect.Parameter.empty
    )
    assert signature.return_annotation == "SteamDTBuffLiveRecipeFixture"
    verified_signature = inspect.signature(
        build_verified_steamdt_buff_live_recipe_fixture
    )
    assert list(verified_signature.parameters) == []
    assert verified_signature.return_annotation == "SteamDTBuffLiveRecipeFixture"
    assert issubclass(SteamDTBuffLiveRecipeFixtureError, ValueError)


def test_verified_builder_only_delegates_with_exact_output_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def capture(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(
        fixture_module,
        "build_steamdt_buff_live_recipe_fixture",
        capture,
    )

    result = build_verified_steamdt_buff_live_recipe_fixture()

    assert result is sentinel
    assert calls == [
        (
            (),
            {
                "output_market_hash_name": (
                    STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
                )
            },
        )
    ]


def test_verified_fixture_locks_name_and_factory_new_wear() -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    construction = fixture.construction_result

    assert len(construction.recipes) == 1
    recipe = construction.recipes[0].recipe
    assert len(recipe.input_items) == 10
    assert len(recipe.tradeup_results) == 1
    canonical_output_names = tuple(
        dict.fromkeys(
            result.output_market_hash_name for result in recipe.tradeup_results
        )
    )
    assert canonical_output_names == (
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
    )
    result = recipe.tradeup_results[0]
    assert result.output_market_hash_name == (
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    )
    assert STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME.endswith(
        "(Factory New)"
    )
    assert result.output_wear == "Factory New"
    assert result.estimated_price_cny == Decimal("0")
    assert result.expected_value_contribution == Decimal("0")


def test_repeated_verified_builds_remain_deterministic_and_synthetic() -> None:
    first = build_verified_steamdt_buff_live_recipe_fixture()
    second = build_verified_steamdt_buff_live_recipe_fixture()

    assert first == second
    assert first is not second
    assert first.construction_result is not second.construction_result
    assert first.solver_config is not second.solver_config
    assert first.risk_config is not second.risk_config
    eligible = first.construction_result.classification.eligible
    assert len(eligible) == 10
    assert all(binding.candidate.source == COMPATIBILITY_SOURCE for binding in eligible)
    assert all(binding.candidate.inspect_link is None for binding in eligible)
    future_lookup_budget = sum(
        len(
            dict.fromkeys(
                result.output_market_hash_name
                for result in live_recipe.recipe.tradeup_results
            )
        )
        for live_recipe in first.construction_result.recipes
    )
    assert future_lookup_budget == 1


def test_result_is_frozen_keyword_only_and_repr_suppressed() -> None:
    fixture = _build()

    with pytest.raises(TypeError):
        SteamDTBuffLiveRecipeFixture(  # type: ignore[misc]
            fixture.construction_result,
            fixture.solver_config,
            fixture.risk_config,
        )
    with pytest.raises(FrozenInstanceError):
        fixture.solver_config = fixture.solver_config  # type: ignore[misc]

    rendered = repr(fixture)
    assert "SteamDTBuffLiveRecipeFixture object" in rendered
    for forbidden in (
        OUTPUT_NAME,
        "construction_result",
        "solver_config",
        "risk_config",
        COMPATIBILITY_SOURCE,
        "1001",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "value",
    [None, 1, "", " ", "  Fixture Output Skin", "Fixture Output Skin  "],
)
def test_output_name_must_be_exact_nonblank_and_already_trimmed(value: object) -> None:
    with pytest.raises(SteamDTBuffLiveRecipeFixtureError) as caught:
        build_steamdt_buff_live_recipe_fixture(  # type: ignore[arg-type]
            output_market_hash_name=value
        )

    assert str(caught.value) == FIXED_ERROR
    assert caught.value.args == (FIXED_ERROR,)
    assert caught.value.__cause__ is None
    if isinstance(value, str) and value.strip():
        assert value not in str(caught.value)


def test_output_name_cannot_collide_with_synthetic_input_name() -> None:
    fixture = _build()
    input_name = fixture.construction_result.recipes[0].recipe.input_items[
        0
    ].market_hash_name

    with pytest.raises(SteamDTBuffLiveRecipeFixtureError, match=f"^{FIXED_ERROR}$"):
        build_steamdt_buff_live_recipe_fixture(output_market_hash_name=input_name)


def test_fixture_has_exact_one_recipe_ten_inputs_and_one_canonical_output() -> None:
    fixture = _build()
    construction = fixture.construction_result

    assert len(construction.recipes) == 1
    live_recipe = construction.recipes[0]
    recipe = live_recipe.recipe
    assert len(recipe.input_items) == 10
    assert len(recipe.tradeup_results) == 1
    canonical_output_names = tuple(
        dict.fromkeys(
            result.output_market_hash_name for result in recipe.tradeup_results
        )
    )
    assert canonical_output_names == (OUTPUT_NAME,)
    assert len(canonical_output_names) == 1


def test_real_engine_derives_probability_float_wear_and_zero_placeholders() -> None:
    fixture = _build()
    result = fixture.construction_result.recipes[0].recipe.tradeup_results[0]

    assert result.output_market_hash_name == OUTPUT_NAME
    assert result.probability == 1.0
    assert math.isfinite(result.output_float)
    assert result.output_float == 0.0625
    assert result.output_wear == "Factory New"
    assert result.estimated_price_cny == Decimal("0")
    assert result.expected_value_contribution == Decimal("0")


def test_output_name_enters_only_the_output_metadata_and_is_solver_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_construct = fixture_module.construct_recipe_selections
    calls: list[tuple[list[object], list[SkinMetadata], RecipeSolverConfig]] = []
    returned: list[list[ConstructedRecipeSelection]] = []

    def capture(
        candidates: list[object],
        skins: list[SkinMetadata],
        config: RecipeSolverConfig,
    ) -> list[ConstructedRecipeSelection]:
        calls.append((candidates, skins, config))
        result = real_construct(candidates, skins, config)  # type: ignore[arg-type]
        returned.append(result)
        return result

    monkeypatch.setattr(fixture_module, "construct_recipe_selections", capture)

    fixture = _build()

    assert len(calls) == 1
    candidates, skins, _config = calls[0]
    assert len(candidates) == 10
    assert all(candidate.market_hash_name != OUTPUT_NAME for candidate in candidates)
    assert len(skins) == 2
    matching = [skin for skin in skins if skin.market_hash_name == OUTPUT_NAME]
    assert len(matching) == 1
    assert matching[0].rarity == "Classified"
    assert skins[0].rarity == "Restricted"
    assert skins[0].market_hash_name != OUTPUT_NAME
    assert len(returned) == 1
    assert fixture.construction_result.recipes[0].recipe == returned[0][0].recipe
    assert (
        fixture.construction_result.recipes[0].recipe.tradeup_results
        == returned[0][0].recipe.tradeup_results
    )


def test_builder_reaches_real_tradeup_engine_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_calculate = recipe_solver_module.calculate_tradeup_results
    calls: list[tuple[list[object], dict[str, list[object]]]] = []
    engine_results: list[list[object]] = []

    def capture(
        input_items: list[object],
        outputs: dict[str, list[object]],
    ):
        calls.append((input_items, outputs))
        result = real_calculate(input_items, outputs)  # type: ignore[arg-type]
        engine_results.append(result)
        return result

    monkeypatch.setattr(recipe_solver_module, "calculate_tradeup_results", capture)

    fixture = _build()

    assert len(calls) == 1
    input_items, outputs = calls[0]
    assert len(input_items) == 10
    assert len(outputs) == 1
    assert sum(len(values) for values in outputs.values()) == 1
    assert len(engine_results) == 1
    assert fixture.construction_result.recipes[0].recipe.tradeup_results == tuple(
        engine_results[0]
    )


def test_candidates_and_selected_order_are_fixed_and_deterministic() -> None:
    fixture = _build()
    construction = fixture.construction_result
    expected_source_ids = tuple(f"{index:064x}" for index in range(1, 11))
    expected_prices = tuple(Decimal(f"{index}.00") for index in range(1, 11))

    assert len(construction.classification.eligible) == 10
    assert construction.classification.rejected == ()
    assert len(construction.classification.buckets) == 1
    assert construction.recipes[0].selected_source_offer_ids == expected_source_ids
    recipe = construction.recipes[0].recipe
    assert tuple(item.price_cny for item in recipe.input_items) == expected_prices
    assert tuple(item.actual_float for item in recipe.input_items) == (0.0625,) * 10
    assert recipe.input_total_cost_cny == Decimal("55.00")
    assert recipe.paint_seeds == tuple(range(1001, 1011))


def test_provenance_is_deterministic_synthetic_compatibility_only() -> None:
    fixture = _build()
    classification = fixture.construction_result.classification
    expected_source_ids = tuple(f"{index:064x}" for index in range(1, 11))

    assert tuple(binding.source_offer_id for binding in classification.eligible) == (
        expected_source_ids
    )
    for binding in classification.eligible:
        source_id = binding.source_offer_id
        candidate = binding.candidate
        assert len(source_id) == 64
        assert source_id == source_id.lower()
        assert all(character in "0123456789abcdef" for character in source_id)
        assert candidate.source == COMPATIBILITY_SOURCE
        assert candidate.goods_id == f"{COMPATIBILITY_SOURCE}:{source_id}"
        assert candidate.listing_id == f"{COMPATIBILITY_SOURCE}:{source_id}"
        assert candidate.inspect_link is None
        assert candidate.raw is None
        assert candidate.scanned_at == datetime(2026, 8, 15, tzinfo=UTC)
        assert not hasattr(candidate, "purchase_link")


def test_solver_and_risk_configs_are_exact_and_construction_only() -> None:
    fixture = _build()

    assert fixture.solver_config == RecipeSolverConfig(
        input_rarity="Restricted",
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        max_candidates_per_collection=10,
        target_stattrak=False,
        target_souvenir=False,
    )
    assert fixture.risk_config == RiskFilterConfig(
        min_roi=Decimal("-1"),
        min_expected_profit_cny=Decimal("-1000"),
        max_worst_case_loss_pct=Decimal("1"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("55.00"),
        min_liquidity_score=None,
        exclude_souvenir=False,
        exclude_stattrak=False,
        exclude_special_pattern_seeds=None,
    )


def test_repeated_builds_are_equal_detached_and_clock_independent() -> None:
    first = _build()
    second = _build()

    assert first == second
    assert first is not second
    assert first.construction_result is not second.construction_result
    assert first.construction_result.recipes[0] is not second.construction_result.recipes[0]
    assert first.solver_config is not second.solver_config
    assert first.risk_config is not second.risk_config
    assert tuple(
        binding.candidate.scanned_at
        for binding in first.construction_result.classification.eligible
    ) == (datetime(2026, 8, 15, tzinfo=UTC),) * 10


def test_future_provider_lookup_budget_is_derived_as_exactly_one() -> None:
    fixture = _build()

    future_lookup_budget = sum(
        len(
            dict.fromkeys(
                result.output_market_hash_name
                for result in live_recipe.recipe.tradeup_results
            )
        )
        for live_recipe in fixture.construction_result.recipes
    )

    assert future_lookup_budget == 1
    assert not hasattr(fixture, "request_budget")
    assert not hasattr(fixture, "price_quote")
    assert not hasattr(fixture, "valuation_result")


def test_direct_result_construction_revalidates_contract() -> None:
    fixture = _build()
    changed_solver = replace(fixture.solver_config, sell_fee_rate=Decimal("0.10"))

    with pytest.raises(SteamDTBuffLiveRecipeFixtureError) as caught:
        SteamDTBuffLiveRecipeFixture(
            construction_result=fixture.construction_result,
            solver_config=changed_solver,
            risk_config=fixture.risk_config,
        )

    assert str(caught.value) == FIXED_ERROR
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("bad_return", [None, (), [], [object()], [object(), object()]])
def test_malformed_solver_return_fails_closed(
    bad_return: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fixture_module,
        "construct_recipe_selections",
        lambda *_args, **_kwargs: bad_return,
    )

    with pytest.raises(SteamDTBuffLiveRecipeFixtureError) as caught:
        _build("Sensitive Output Name")

    assert str(caught.value) == FIXED_ERROR
    assert caught.value.__cause__ is None
    assert "Sensitive Output Name" not in str(caught.value)


def test_unknown_selected_listing_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_construct = fixture_module.construct_recipe_selections

    def alter(candidates, skins, config):
        original = real_construct(candidates, skins, config)[0]
        return [
            ConstructedRecipeSelection(
                recipe=original.recipe,
                selected_listing_ids=(
                    "unknown-synthetic-listing",
                    *original.selected_listing_ids[1:],
                ),
            )
        ]

    monkeypatch.setattr(fixture_module, "construct_recipe_selections", alter)

    with pytest.raises(SteamDTBuffLiveRecipeFixtureError, match=f"^{FIXED_ERROR}$"):
        _build()


def test_reordered_selected_identities_fail_alignment_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_construct = fixture_module.construct_recipe_selections

    def reorder(candidates, skins, config):
        original = real_construct(candidates, skins, config)[0]
        return [
            ConstructedRecipeSelection(
                recipe=original.recipe,
                selected_listing_ids=tuple(reversed(original.selected_listing_ids)),
            )
        ]

    monkeypatch.setattr(fixture_module, "construct_recipe_selections", reorder)

    with pytest.raises(SteamDTBuffLiveRecipeFixtureError, match=f"^{FIXED_ERROR}$"):
        _build()


class DirectControlFlow(BaseException):
    pass


@pytest.mark.parametrize(
    "failure",
    [MemoryError("memory"), KeyboardInterrupt(), SystemExit(7), DirectControlFlow("stop")],
)
def test_process_control_failures_propagate_by_identity(
    failure: BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(fixture_module, "construct_recipe_selections", fail)

    try:
        _build()
    except BaseException as caught:
        assert caught is failure
    else:
        raise AssertionError("process-control failure should propagate")


def test_verified_wrapper_ast_is_exact_single_delegation() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wrappers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_verified_steamdt_buff_live_recipe_fixture"
    ]

    assert len(wrappers) == 1
    wrapper = wrappers[0]
    assert wrapper.args.posonlyargs == []
    assert wrapper.args.args == []
    assert wrapper.args.vararg is None
    assert wrapper.args.kwonlyargs == []
    assert wrapper.args.kw_defaults == []
    assert wrapper.args.kwarg is None
    executable_body = wrapper.body
    if (
        executable_body
        and isinstance(executable_body[0], ast.Expr)
        and isinstance(executable_body[0].value, ast.Constant)
        and isinstance(executable_body[0].value.value, str)
    ):
        executable_body = executable_body[1:]
    assert len(executable_body) == 1
    assert isinstance(executable_body[0], ast.Return)
    delegated = executable_body[0].value
    assert isinstance(delegated, ast.Call)
    assert isinstance(delegated.func, ast.Name)
    assert delegated.func.id == "build_steamdt_buff_live_recipe_fixture"
    assert delegated.args == []
    assert len(delegated.keywords) == 1
    keyword = delegated.keywords[0]
    assert keyword.arg == "output_market_hash_name"
    assert isinstance(keyword.value, ast.Name)
    assert keyword.value.id == (
        "STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME"
    )


def test_production_fixture_omits_historical_price_and_runtime_values() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "539.88" not in source
    for forbidden in (
        "PriceQuote",
        "SteamDTBuffPriceProvider",
        "SteamDTMarketDataClient",
        "ValuationService",
        "value_live_recipes",
        "evaluate_opportunity",
    ):
        assert forbidden not in source


def test_module_has_no_handwritten_tradeup_geometry_or_runtime_boundary() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    names: set[str] = set()
    called_terminals: list[str] = []
    geometry_keywords: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_terminals.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_terminals.append(node.func.attr)
            geometry_keywords.update(
                keyword.arg for keyword in node.keywords if keyword.arg is not None
            )

    assert imports == {
        "__future__",
        "math",
        "dataclasses",
        "datetime",
        "decimal",
        "app.services.live_metadata_catalog",
        "app.services.live_recipe_construction",
        "app.services.market_scan_service",
        "app.services.metadata_models",
        "app.services.recipe_solver",
        "app.services.risk_filter",
        "LiveCandidateBinding",
        "LiveCandidateClassification",
        "LiveSolverBucket",
        "LiveSolverBucketKey",
        "LiveConstructedRecipe",
        "LiveRecipeConstructionResult",
        "CandidateListing",
        "SkinMetadata",
        "ConstructedRecipeSelection",
        "RecipeSolverConfig",
        "construct_recipe_selections",
        "RiskFilterConfig",
        "annotations",
        "dataclass",
        "UTC",
        "Decimal",
    }
    forbidden_names = {
        "TradeupResult",
        "InputItem",
        "OutputCandidate",
        "ConstructedRecipe",
        "calculate_tradeup_results",
        "calculate_output_float",
        "get_wear_name",
        "solve_recipes",
        "construct_recipes",
        "SteamDTBuffPriceProvider",
        "PriceQuote",
        "ValuationService",
        "value_live_recipes",
        "value_live_recipes_with_steamdt_buff_prices",
        "calculate_opportunity_metrics",
        "evaluate_opportunity",
        "SteamApisListingObservation",
        "SteamApisOfferPool",
        "SteamApisOfferPoolSnapshot",
    }
    assert names.isdisjoint(forbidden_names)
    assert set(called_terminals).isdisjoint(forbidden_names)
    assert called_terminals.count("construct_recipe_selections") == 1
    assert {
        "probability",
        "output_float",
        "output_wear",
        "estimated_price_cny",
        "expected_value_contribution",
    }.isdisjoint(geometry_keywords)


def test_module_has_no_env_network_observation_purchase_or_nondeterminism() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    folded = source.casefold()
    for forbidden in (
        "datetime.now",
        "utcnow",
        "date.today",
        "random",
        "uuid",
        "secrets",
        "os.environ",
        "getenv",
        "httpx",
        "requests",
        "websocket",
        "redis",
        "scheduler",
        "create_task",
        "thread",
        "steamapislistingobservation",
        "steamapisofferpool",
        "purchase_link",
        "inspect_link=\"",
        "raw={",
        "open(",
        "read_text",
        "write_text",
        ".split(",
        ".partition(",
        ".removeprefix(",
    ):
        assert forbidden not in folded
    steamapis_literals = [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "steamapis" in node.value.casefold()
    ]
    assert steamapis_literals == [COMPATIBILITY_SOURCE]


def test_fixture_is_not_reverse_imported_by_protected_authorities() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture_name = "steamdt_buff_live_recipe_fixture"
    protected = [
        project_root / "app" / "services" / "tradeup_engine.py",
        project_root / "app" / "services" / "recipe_solver.py",
        project_root / "app" / "services" / "live_metadata_catalog.py",
        project_root / "app" / "services" / "live_recipe_construction.py",
        project_root / "app" / "services" / "live_recipe_valuation.py",
        project_root / "app" / "services" / "steamdt_buff_price_provider.py",
        project_root / "app" / "services" / "steamdt_buff_live_recipe_valuation.py",
        project_root / "app" / "jobs" / "scheduler.py",
        project_root / "app" / "main.py",
    ]

    for path in protected:
        assert fixture_name not in path.read_text(encoding="utf-8")
