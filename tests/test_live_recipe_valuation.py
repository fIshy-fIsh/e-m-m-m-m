from __future__ import annotations

import ast
import asyncio
import inspect
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

import app.services.live_recipe_valuation as live_module
from app.services.ev_service import OpportunityMetrics
from app.services.live_metadata_catalog import (
    LiveCandidateBinding,
    LiveCandidateClassification,
    LiveSolverBucket,
    LiveSolverBucketKey,
)
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionResult,
)
from app.services.live_recipe_valuation import (
    LiveRecipeValuationError,
    LiveRecipeValuationRejection,
    LiveRecipeValuationRejectionReason,
    LiveRecipeValuationResult,
    LiveValuedOpportunity,
    value_live_recipes,
)
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceQuote,
)
from app.services.recipe_solver import ConstructedRecipe, RecipeSolverConfig
from app.services.risk_filter import RiskDecision, RiskFilterConfig
from app.services.tradeup_engine import InputItem, TradeupResult
from app.services.valuation_service import (
    ValuationConfig,
    ValuationMissingPriceStrategy,
    ValuationResult,
    ValuationService,
    ValuationWarning,
)

MODULE_PATH = Path("app/services/live_recipe_valuation.py")
_SOURCE = "steamapis:buff163"


def _source_id(index: int) -> str:
    return f"{index:064x}"


def _input_item(index: int) -> InputItem:
    return InputItem(
        market_hash_name=f"Input {index}",
        collection_name="Collection Alpha" if index < 5 else "Collection Beta",
        rarity="Restricted",
        actual_float=0.10 + index / 1000,
        min_float=0.0,
        max_float=1.0,
        price_cny=Decimal("10.00") + Decimal(index),
        stattrak=False,
        souvenir=False,
    )


def _original_result(
    name: str,
    probability: float,
    output_float: float,
    wear: str,
) -> TradeupResult:
    return TradeupResult(
        output_market_hash_name=name,
        probability=probability,
        output_float=output_float,
        output_wear=wear,
        estimated_price_cny=Decimal("0"),
        expected_value_contribution=Decimal("0"),
    )


def _build_construction_result(
    *,
    recipe_count: int = 1,
) -> LiveRecipeConstructionResult:
    bindings: list[LiveCandidateBinding] = []
    live_recipes: list[LiveConstructedRecipe] = []

    for recipe_index in range(recipe_count):
        recipe_bindings: list[LiveCandidateBinding] = []
        input_items: list[InputItem] = []
        source_ids: list[str] = []
        for item_index in range(10):
            global_index = recipe_index * 10 + item_index + 1
            source_id = _source_id(global_index)
            source_ids.append(source_id)
            input_item = _input_item(item_index)
            input_items.append(input_item)
            candidate = CandidateListing(
                goods_id=f"{_SOURCE}:{source_id}",
                listing_id=f"{_SOURCE}:{source_id}",
                market_hash_name=input_item.market_hash_name,
                price_cny=input_item.price_cny,
                float_value=input_item.actual_float,
                paint_seed=1000 + global_index,
                inspect_link=None,
                source=_SOURCE,
                raw=None,
            )
            skin = SkinMetadata(
                market_hash_name=input_item.market_hash_name,
                name=None,
                weapon=None,
                rarity=input_item.rarity,
                category=None,
                collection_name=input_item.collection_name,
                min_float=input_item.min_float,
                max_float=input_item.max_float,
                stattrak=False,
                souvenir=False,
                paint_index=None,
                raw=None,
            )
            binding = LiveCandidateBinding(
                source_offer_id=source_id,
                candidate=candidate,
                skin_metadata=skin,
            )
            bindings.append(binding)
            recipe_bindings.append(binding)

        first_probability = 0.4 if recipe_index == 0 else 0.25
        original_results = (
            _original_result("Output Alpha", first_probability, 0.12, "Minimal Wear"),
            _original_result(
                "Output Beta",
                1.0 - first_probability,
                0.24,
                "Field-Tested",
            ),
        )
        recipe = ConstructedRecipe(
            input_items=tuple(input_items),
            tradeup_results=original_results,
            paint_seeds=tuple(
                binding.candidate.paint_seed
                for binding in recipe_bindings
                if binding.candidate.paint_seed is not None
            ),
        )
        live_recipes.append(
            LiveConstructedRecipe(
                recipe=recipe,
                selected_source_offer_ids=tuple(source_ids),
            )
        )

    key = LiveSolverBucketKey(
        input_rarity="Restricted",
        stattrak=False,
        souvenir=False,
    )
    bucket = LiveSolverBucket(
        key=key,
        bindings=tuple(bindings),
        affected_collections=frozenset({"Collection Alpha", "Collection Beta"}),
    )
    classification = LiveCandidateClassification(
        eligible=tuple(bindings),
        rejected=(),
        buckets=(bucket,),
    )
    return LiveRecipeConstructionResult(
        classification=classification,
        recipes=tuple(live_recipes),
    )


def _quotes(prices: tuple[str, str] = ("300", "100")) -> dict[str, PriceQuote]:
    return {
        "Output Alpha": PriceQuote(
            market_hash_name="Output Alpha",
            price_cny=Decimal(prices[0]),
            source="synthetic",
        ),
        "Output Beta": PriceQuote(
            market_hash_name="Output Beta",
            price_cny=Decimal(prices[1]),
            source="synthetic",
        ),
    }


def _service(
    *,
    quotes: dict[str, PriceQuote] | None = None,
    config: ValuationConfig | None = None,
) -> ValuationService:
    return ValuationService(
        MockPriceProvider(quotes_by_name=_quotes() if quotes is None else quotes),
        config,
    )


def _solver_config() -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity="Restricted",
        sell_fee_rate=Decimal("0.025"),
    )


def _risk_config(**overrides: object) -> RiskFilterConfig:
    values: dict[str, object] = {
        "min_roi": Decimal("-1"),
        "min_expected_profit_cny": Decimal("-1000"),
        "max_worst_case_loss_pct": Decimal("2"),
        "min_profit_probability": 0.0,
        "max_input_total_cost_cny": Decimal("10000"),
    }
    values.update(overrides)
    return RiskFilterConfig(**values)  # type: ignore[arg-type]


def _run(
    construction: LiveRecipeConstructionResult | None = None,
    service: ValuationService | None = None,
    risk_config: RiskFilterConfig | None = None,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult:
    return asyncio.run(
        value_live_recipes(
            construction_result=construction or _build_construction_result(),
            valuation_service=service or _service(),
            solver_config=_solver_config(),
            risk_config=risk_config or _risk_config(),
            liquidity_score=liquidity_score,
        )
    )


def _complete_valuation(
    originals: list[TradeupResult],
    *,
    prices: tuple[str, str] = ("300", "100"),
) -> ValuationResult:
    quotes = _quotes(prices)
    valued = [
        replace(
            result,
            estimated_price_cny=quotes[result.output_market_hash_name].price_cny,
            expected_value_contribution=(
                quotes[result.output_market_hash_name].price_cny
                * Decimal(str(result.probability))
            ),
        )
        for result in originals
    ]
    return ValuationResult(
        tradeup_results=valued,
        missing_market_hash_names=[],
        warnings=[],
        price_lookup_result=PriceLookupResult(
            quotes=quotes,
            missing=[],
            errors=[],
        ),
    )


class ReturningValuationService(ValuationService):
    def __init__(self, returned: object) -> None:
        super().__init__(MockPriceProvider())
        self.returned = returned
        self.calls: list[list[TradeupResult]] = []

    async def value_tradeup_results(
        self,
        tradeup_results: list[TradeupResult],
    ) -> ValuationResult:
        self.calls.append(list(tradeup_results))
        return cast(ValuationResult, self.returned)


class RaisingValuationService(ValuationService):
    def __init__(self, error: BaseException) -> None:
        super().__init__(MockPriceProvider())
        self.error = error

    async def value_tradeup_results(
        self,
        tradeup_results: list[TradeupResult],
    ) -> ValuationResult:
        raise self.error


def test_public_contract_is_exact() -> None:
    assert live_module.__all__ == (
        "LiveRecipeValuationError",
        "LiveRecipeValuationRejectionReason",
        "LiveValuedOpportunity",
        "LiveRecipeValuationRejection",
        "LiveRecipeValuationResult",
        "value_live_recipes",
    )
    assert [field.name for field in fields(LiveValuedOpportunity)] == [
        "recipe",
        "selected_source_offer_ids",
        "valued_tradeup_results",
        "metrics",
        "risk_decision",
    ]
    assert [field.name for field in fields(LiveRecipeValuationRejection)] == [
        "selected_source_offer_ids",
        "reason_code",
    ]
    assert [field.name for field in fields(LiveRecipeValuationResult)] == [
        "opportunities",
        "rejected",
    ]
    assert list(LiveRecipeValuationRejectionReason) == [
        LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE,
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR,
        LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT,
    ]
    signature = inspect.signature(value_live_recipes)
    assert inspect.iscoroutinefunction(value_live_recipes)
    assert list(signature.parameters) == [
        "construction_result",
        "valuation_service",
        "solver_config",
        "risk_config",
        "liquidity_score",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )


def test_public_dtos_are_frozen_keyword_only_and_repr_safe() -> None:
    construction = _build_construction_result()
    result = _run(construction)
    opportunity = result.opportunities[0]
    rejection = LiveRecipeValuationRejection(
        selected_source_offer_ids=construction.recipes[0].selected_source_offer_ids,
        reason_code=LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE,
    )

    for value in (opportunity, rejection, result):
        representation = repr(value)
        assert " object at " in representation
        assert "Output" not in representation
        assert construction.recipes[0].selected_source_offer_ids[0] not in representation
        with pytest.raises(FrozenInstanceError):
            setattr(value, next(iter(value.__dict__)), None)

    with pytest.raises(TypeError):
        LiveRecipeValuationResult((), ())  # type: ignore[misc]


def test_happy_path_uses_complete_prices_and_authoritative_metrics() -> None:
    construction = _build_construction_result()
    result = _run(construction)

    assert result.rejected == ()
    assert len(result.opportunities) == 1
    opportunity = result.opportunities[0]
    assert opportunity.recipe == construction.recipes[0].recipe
    assert opportunity.selected_source_offer_ids == (
        construction.recipes[0].selected_source_offer_ids
    )
    assert [item.estimated_price_cny for item in opportunity.valued_tradeup_results] == [
        Decimal("300"),
        Decimal("100"),
    ]
    assert [
        item.expected_value_contribution
        for item in opportunity.valued_tradeup_results
    ] == [Decimal("120.0"), Decimal("60.0")]
    assert opportunity.metrics.input_total_cost_cny == Decimal("145.00")
    assert opportunity.metrics.expected_revenue_cny == Decimal("180.0")
    assert opportunity.metrics.expected_profit_cny == Decimal("30.5000")
    assert opportunity.metrics.roi == Decimal("30.5000") / Decimal("145.00")
    assert opportunity.metrics.profit_probability == pytest.approx(0.4)
    assert opportunity.metrics.loss_probability == pytest.approx(0.6)
    assert opportunity.metrics.break_even_probability == 0
    assert opportunity.metrics.worst_case_profit_cny == Decimal("-47.500")
    assert opportunity.metrics.best_case_profit_cny == Decimal("147.500")


def test_geometry_placeholders_and_inputs_remain_unchanged() -> None:
    construction = _build_construction_result()
    original_recipe = construction.recipes[0].recipe
    opportunity = _run(construction).opportunities[0]

    assert opportunity.recipe == original_recipe
    assert all(
        result.estimated_price_cny == 0
        for result in opportunity.recipe.tradeup_results
    )
    for original, valued in zip(
        original_recipe.tradeup_results,
        opportunity.valued_tradeup_results,
        strict=True,
    ):
        assert valued.output_market_hash_name == original.output_market_hash_name
        assert valued.probability == original.probability
        assert valued.output_float == original.output_float
        assert valued.output_wear == original.output_wear
    assert opportunity.recipe.input_items == original_recipe.input_items
    assert opportunity.recipe.paint_seeds == original_recipe.paint_seeds


def test_real_paint_seeds_and_liquidity_reach_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    construction = _build_construction_result()
    captured: dict[str, object] = {}
    real_evaluator = live_module.evaluate_opportunity

    def capturing_evaluator(**kwargs: object) -> RiskDecision:
        captured.update(kwargs)
        return real_evaluator(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(live_module, "evaluate_opportunity", capturing_evaluator)
    liquidity = Decimal("0.75")
    _run(construction, liquidity_score=liquidity)

    assert captured["paint_seeds"] == list(
        construction.recipes[0].recipe.paint_seeds
    )
    assert captured["paint_seeds"] is not None
    assert captured["liquidity_score"] == liquidity


def test_excluded_real_seed_fails_risk_but_remains_opportunity() -> None:
    construction = _build_construction_result()
    excluded = construction.recipes[0].recipe.paint_seeds[3]
    result = _run(
        construction,
        risk_config=_risk_config(exclude_special_pattern_seeds={excluded}),
    )

    assert result.rejected == ()
    assert len(result.opportunities) == 1
    decision = result.opportunities[0].risk_decision
    assert decision.passed is False
    assert "SPECIAL_PATTERN_SEED_EXCLUDED" in decision.reason_codes


def test_repeated_happy_path_is_deterministic_and_does_not_mutate_inputs() -> None:
    construction = _build_construction_result()
    risk = _risk_config(exclude_special_pattern_seeds={999999})
    before = construction
    first = _run(construction, risk_config=risk)
    second = _run(construction, risk_config=risk)

    assert first == second
    assert construction == before
    assert risk.exclude_special_pattern_seeds == {999999}


@pytest.mark.parametrize(
    ("quotes", "config"),
    [
        (
            {"Output Alpha": _quotes()["Output Alpha"]},
            ValuationConfig(
                missing_price_strategy=ValuationMissingPriceStrategy.KEEP_ORIGINAL
            ),
        ),
        (
            {},
            ValuationConfig(
                missing_price_strategy=ValuationMissingPriceStrategy.ZERO_PRICE
            ),
        ),
        (
            {},
            ValuationConfig(
                missing_price_strategy=ValuationMissingPriceStrategy.DROP_RESULT
            ),
        ),
        ({}, ValuationConfig(require_all_prices=True)),
    ],
)
def test_every_missing_strategy_rejects_whole_recipe(
    quotes: dict[str, PriceQuote],
    config: ValuationConfig,
) -> None:
    result = _run(service=_service(quotes=quotes, config=config))

    assert result.opportunities == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE
    )


def test_provider_errors_take_precedence_over_missing_and_malformed_outputs() -> None:
    construction = _build_construction_result()
    original = list(construction.recipes[0].recipe.tradeup_results)
    malformed = ValuationResult(
        tradeup_results=original[:1],
        missing_market_hash_names=["Output Beta"],
        warnings=[ValuationWarning(code="PRICE_PROVIDER_ERROR", message="secret")],
        price_lookup_result=PriceLookupResult(
            quotes={},
            missing=["Output Alpha", "Output Beta"],
            errors=["Cookie=dummy-cookie"],
        ),
    )

    result = _run(construction, ReturningValuationService(malformed))

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    )
    assert "secret" not in repr(result)
    assert "dummy-cookie" not in repr(result)


def test_direct_ordinary_service_exception_is_redacted_provider_rejection() -> None:
    result = _run(service=RaisingValuationService(RuntimeError("API key=dummy")))

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    )
    assert "dummy" not in repr(result)


def test_undeclared_missing_quote_is_missing_price() -> None:
    construction = _build_construction_result()
    original = list(construction.recipes[0].recipe.tradeup_results)
    valuation = _complete_valuation(original)
    valuation.price_lookup_result.quotes.pop("Output Beta")

    result = _run(construction, ReturningValuationService(valuation))

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: replace(value, tradeup_results=value.tradeup_results[:1]),
        lambda value: replace(
            value,
            tradeup_results=list(reversed(value.tradeup_results)),
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], output_market_hash_name="Changed"),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], probability=0.5),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], output_float=0.13),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], output_wear="Changed Wear"),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], estimated_price_cny=Decimal("NaN")),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(value.tradeup_results[0], estimated_price_cny=Decimal("-1")),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            tradeup_results=[
                replace(
                    value.tradeup_results[0],
                    expected_value_contribution=Decimal("999"),
                ),
                value.tradeup_results[1],
            ],
        ),
        lambda value: replace(
            value,
            price_lookup_result=replace(
                value.price_lookup_result,
                quotes={
                    **value.price_lookup_result.quotes,
                    "Extra": PriceQuote(
                        market_hash_name="Extra",
                        price_cny=Decimal("1"),
                        source="synthetic",
                    ),
                },
            ),
        ),
        lambda value: replace(
            value,
            price_lookup_result=replace(
                value.price_lookup_result,
                quotes={
                    **value.price_lookup_result.quotes,
                    "Output Alpha": replace(
                        value.price_lookup_result.quotes["Output Alpha"],
                        market_hash_name="Other",
                    ),
                },
            ),
        ),
        lambda value: replace(
            value,
            price_lookup_result=replace(
                value.price_lookup_result,
                quotes={
                    **value.price_lookup_result.quotes,
                    "Output Alpha": replace(
                        value.price_lookup_result.quotes["Output Alpha"],
                        price_cny=Decimal("301"),
                    ),
                },
            ),
        ),
        lambda value: replace(
            value,
            warnings=[ValuationWarning(code="UNKNOWN", message="opaque")],
        ),
    ],
)
def test_malformed_valuation_is_rejected_without_partial_opportunity(mutator) -> None:
    construction = _build_construction_result()
    original = list(construction.recipes[0].recipe.tradeup_results)
    valuation = mutator(_complete_valuation(original))

    result = _run(construction, ReturningValuationService(valuation))

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT
    )


def test_wrong_top_level_valuation_type_is_invalid() -> None:
    result = _run(service=ReturningValuationService(object()))

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT
    )


def test_malformed_signal_containers_are_invalid_not_misclassified() -> None:
    construction = _build_construction_result()
    original = list(construction.recipes[0].recipe.tradeup_results)
    complete = _complete_valuation(original)
    malformed_errors = replace(
        complete,
        price_lookup_result=PriceLookupResult(
            quotes=complete.price_lookup_result.quotes,
            missing=[],
            errors=[cast(str, object())],
        ),
    )
    malformed_warning = replace(
        complete,
        warnings=[cast(ValuationWarning, object())],
    )

    for valuation in (malformed_errors, malformed_warning):
        result = _run(construction, ReturningValuationService(valuation))
        assert result.opportunities == ()
        assert result.rejected[0].reason_code is (
            LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT
        )


def test_quoted_zero_price_is_valid_but_missing_zero_never_is() -> None:
    quotes = _quotes(("0", "100"))
    complete = _run(service=_service(quotes=quotes))
    missing = _run(
        service=_service(
            quotes={"Output Beta": quotes["Output Beta"]},
            config=ValuationConfig(
                missing_price_strategy=ValuationMissingPriceStrategy.ZERO_PRICE
            ),
        )
    )

    assert complete.opportunities[0].valued_tradeup_results[0].estimated_price_cny == 0
    assert missing.opportunities == ()
    assert missing.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE
    )


def test_business_rejection_skips_metrics_and_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("downstream must not run")

    monkeypatch.setattr(live_module, "calculate_opportunity_metrics", forbidden)
    monkeypatch.setattr(live_module, "evaluate_opportunity", forbidden)

    result = _run(service=_service(quotes={}))

    assert result.opportunities == ()
    assert len(result.rejected) == 1


def test_multiple_recipes_are_sequential_and_independent() -> None:
    construction = _build_construction_result(recipe_count=2)

    class SequentialService(ValuationService):
        def __init__(self) -> None:
            super().__init__(MockPriceProvider())
            self.active = False
            self.calls: list[float] = []

        async def value_tradeup_results(
            self,
            tradeup_results: list[TradeupResult],
        ) -> ValuationResult:
            assert self.active is False
            self.active = True
            self.calls.append(tradeup_results[0].probability)
            await asyncio.sleep(0)
            self.active = False
            if len(self.calls) == 1:
                return ValuationResult(
                    tradeup_results=tradeup_results,
                    missing_market_hash_names=["Output Alpha"],
                    warnings=[],
                    price_lookup_result=PriceLookupResult(
                        quotes={},
                        missing=["Output Alpha"],
                        errors=[],
                    ),
                )
            return _complete_valuation(tradeup_results)

    service = SequentialService()
    result = _run(construction, service)

    assert service.calls == [0.4, 0.25]
    assert len(result.rejected) == 1
    assert len(result.opportunities) == 1
    assert result.rejected[0].selected_source_offer_ids == (
        construction.recipes[0].selected_source_offer_ids
    )
    assert result.opportunities[0].selected_source_offer_ids == (
        construction.recipes[1].selected_source_offer_ids
    )


def test_empty_construction_calls_nothing() -> None:
    original = _build_construction_result()
    construction = LiveRecipeConstructionResult(
        classification=original.classification,
        recipes=(),
    )
    service = ReturningValuationService(object())

    result = _run(construction, service)

    assert result == LiveRecipeValuationResult(opportunities=(), rejected=())
    assert service.calls == []


def test_late_metrics_failure_is_fixed_atomic_orchestration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction = _build_construction_result(recipe_count=2)
    real_metrics = live_module.calculate_opportunity_metrics
    calls = 0

    def failing_second(**kwargs: object) -> OpportunityMetrics:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("market=secret price=999")
        return real_metrics(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(live_module, "calculate_opportunity_metrics", failing_second)

    with pytest.raises(LiveRecipeValuationError) as captured:
        _run(construction)

    assert str(captured.value) == "invalid live recipe valuation contract"
    assert captured.value.__cause__ is None
    assert "secret" not in repr(captured.value)


def test_risk_failure_is_fixed_orchestration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_risk(**kwargs: object) -> RiskDecision:
        raise RuntimeError("Cookie=dummy-cookie source-id=dummy")

    monkeypatch.setattr(live_module, "evaluate_opportunity", failing_risk)

    with pytest.raises(LiveRecipeValuationError) as captured:
        _run()

    assert str(captured.value) == "invalid live recipe valuation contract"
    assert captured.value.__cause__ is None
    assert "dummy" not in repr(captured.value)


@pytest.mark.parametrize(
    "error",
    [MemoryError("memory"), KeyboardInterrupt("keyboard"), asyncio.CancelledError("cancel")],
)
def test_control_flow_failures_propagate_by_identity(error: BaseException) -> None:
    with pytest.raises(type(error)) as captured:
        _run(service=RaisingValuationService(error))

    assert captured.value is error


def test_result_and_nested_reason_lists_are_detached() -> None:
    result = _run(risk_config=_risk_config(min_roi=Decimal("99")))
    decision = result.opportunities[0].risk_decision
    copied = LiveRecipeValuationResult(
        opportunities=result.opportunities,
        rejected=result.rejected,
    )

    decision.reasons.append("mutated")
    decision.reason_codes.append("MUTATED")

    assert "mutated" not in copied.opportunities[0].risk_decision.reasons
    assert "MUTATED" not in copied.opportunities[0].risk_decision.reason_codes


def test_architecture_has_no_construction_external_or_background_boundary() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden_calls = {
        "solve_recipes",
        "construct_recipes",
        "construct_recipe_selections",
        "construct_live_recipes",
        "calculate_tradeup_results",
        "create_task",
        "gather",
        "to_thread",
    }
    forbidden_markers = {
        "steamdt",
        "steamapis",
        "buffclient",
        "redis",
        "websocket",
        "discord",
        "httpx",
        "requests",
        "fastapi",
        "scheduler",
        "purchase_link",
        "purchaselink",
        "inspect_link",
        "inspectlink",
        "os.environ",
        "getenv",
    }

    assert calls.isdisjoint(forbidden_calls)
    normalized_imports = " ".join(imports).lower()
    assert all(marker not in normalized_imports for marker in forbidden_markers)
    normalized_source = source.lower()
    assert all(marker not in normalized_source for marker in forbidden_markers)


def test_only_authoritative_metrics_and_risk_primitives_are_imported() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert source.count("calculate_opportunity_metrics(") == 1
    assert source.count("evaluate_opportunity(") == 1
    assert "sell_fee_rate=solver.sell_fee_rate" in source
    assert "paint_seeds=list(live_recipe.recipe.paint_seeds)" in source
