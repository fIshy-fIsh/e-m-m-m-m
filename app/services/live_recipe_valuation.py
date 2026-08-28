from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.services.ev_service import (
    PROBABILITY_TOLERANCE,
    OpportunityMetrics,
    calculate_opportunity_metrics,
)
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionResult,
)
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_solver import ConstructedRecipe, RecipeSolverConfig
from app.services.risk_filter import (
    RiskDecision,
    RiskFilterConfig,
    evaluate_opportunity,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import (
    ValuationResult,
    ValuationService,
    ValuationWarning,
)

_FIXED_ERROR_MESSAGE = "invalid live recipe valuation contract"
_MISSING_WARNING_CODES = frozenset(
    {
        "MISSING_PRICE_KEEP_ORIGINAL",
        "MISSING_PRICE_ZEROED",
        "MISSING_PRICE_DROPPED",
        "REQUIRE_ALL_PRICES_NOT_SATISFIED",
    }
)

__all__ = (
    "LiveRecipeValuationError",
    "LiveRecipeValuationRejectionReason",
    "LiveValuedOpportunity",
    "LiveRecipeValuationRejection",
    "LiveRecipeValuationResult",
    "value_live_recipes",
)


class LiveRecipeValuationError(ValueError):
    """A value or operation violated the live valuation contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


class LiveRecipeValuationRejectionReason(StrEnum):
    """Stable reasons why a complete live valuation was not available."""

    MISSING_OUTPUT_PRICE = "missing_output_price"
    PRICE_PROVIDER_ERROR = "price_provider_error"
    INVALID_VALUATION_RESULT = "invalid_valuation_result"


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveValuedOpportunity:
    """One completely valued live recipe with metrics, risk, and provenance."""

    recipe: ConstructedRecipe
    selected_source_offer_ids: tuple[str, ...]
    valued_tradeup_results: tuple[TradeupResult, ...]
    metrics: OpportunityMetrics
    risk_decision: RiskDecision

    def __post_init__(self) -> None:
        try:
            live_recipe = _copy_live_recipe(
                LiveConstructedRecipe(
                    recipe=self.recipe,
                    selected_source_offer_ids=self.selected_source_offer_ids,
                )
            )
            valued_results = _copy_complete_valued_results(
                self.valued_tradeup_results,
                live_recipe.recipe.tradeup_results,
            )
            metrics = _copy_metrics(self.metrics)
            risk_decision = _copy_risk_decision(self.risk_decision)
            if metrics.input_total_cost_cny != live_recipe.recipe.input_total_cost_cny:
                raise LiveRecipeValuationError
            expected_revenue = sum(
                (result.expected_value_contribution for result in valued_results),
                start=Decimal("0"),
            )
            if metrics.expected_revenue_cny != expected_revenue:
                raise LiveRecipeValuationError
            object.__setattr__(self, "recipe", live_recipe.recipe)
            object.__setattr__(
                self,
                "selected_source_offer_ids",
                live_recipe.selected_source_offer_ids,
            )
            object.__setattr__(self, "valued_tradeup_results", valued_results)
            object.__setattr__(self, "metrics", metrics)
            object.__setattr__(self, "risk_decision", risk_decision)
        except MemoryError:
            raise
        except Exception:
            raise LiveRecipeValuationError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveRecipeValuationRejection:
    """One live recipe rejected before complete opportunity evaluation."""

    selected_source_offer_ids: tuple[str, ...]
    reason_code: LiveRecipeValuationRejectionReason

    def __post_init__(self) -> None:
        try:
            source_offer_ids = _copy_source_offer_ids(self.selected_source_offer_ids)
            if type(self.reason_code) is not LiveRecipeValuationRejectionReason:
                raise LiveRecipeValuationError
            object.__setattr__(self, "selected_source_offer_ids", source_offer_ids)
        except MemoryError:
            raise
        except Exception:
            raise LiveRecipeValuationError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveRecipeValuationResult:
    """Ordered successful and rejected results from one offline valuation pass."""

    opportunities: tuple[LiveValuedOpportunity, ...]
    rejected: tuple[LiveRecipeValuationRejection, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.opportunities) is not tuple or type(self.rejected) is not tuple:
                raise LiveRecipeValuationError
            opportunities = tuple(
                _copy_opportunity(opportunity) for opportunity in self.opportunities
            )
            rejected = tuple(_copy_rejection(item) for item in self.rejected)
            selected_ids = [
                source_offer_id
                for selected in (
                    *(
                        opportunity.selected_source_offer_ids
                        for opportunity in opportunities
                    ),
                    *(item.selected_source_offer_ids for item in rejected),
                )
                for source_offer_id in selected
            ]
            if len(selected_ids) != len(set(selected_ids)):
                raise LiveRecipeValuationError
            object.__setattr__(self, "opportunities", opportunities)
            object.__setattr__(self, "rejected", rejected)
        except MemoryError:
            raise
        except Exception:
            raise LiveRecipeValuationError from None


async def value_live_recipes(
    *,
    construction_result: LiveRecipeConstructionResult,
    valuation_service: ValuationService,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult:
    """Value already-constructed live recipes with strict complete-price gates."""

    try:
        construction = _copy_construction_result(construction_result)
        service = _validate_valuation_service(valuation_service)
        solver = _copy_solver_config(solver_config)
        risk = _copy_risk_config(risk_config)
        liquidity = _copy_optional_decimal(liquidity_score)
        opportunities: list[LiveValuedOpportunity] = []
        rejected: list[LiveRecipeValuationRejection] = []

        for live_recipe in construction.recipes:
            try:
                valuation = await service.value_tradeup_results(
                    list(live_recipe.recipe.tradeup_results)
                )
            except MemoryError:
                raise
            except Exception:
                rejected.append(
                    _build_rejection(
                        live_recipe,
                        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR,
                    )
                )
                continue

            validated = _validate_complete_valuation(
                valuation,
                live_recipe.recipe.tradeup_results,
            )
            if isinstance(validated, LiveRecipeValuationRejectionReason):
                rejected.append(_build_rejection(live_recipe, validated))
                continue

            input_items = list(live_recipe.recipe.input_items)
            valued_results = list(validated)
            metrics = calculate_opportunity_metrics(
                input_items=input_items,
                tradeup_results=valued_results,
                sell_fee_rate=solver.sell_fee_rate,
            )
            risk_decision = evaluate_opportunity(
                metrics=metrics,
                input_items=input_items,
                config=risk,
                liquidity_score=liquidity,
                paint_seeds=list(live_recipe.recipe.paint_seeds),
            )
            opportunities.append(
                LiveValuedOpportunity(
                    recipe=live_recipe.recipe,
                    selected_source_offer_ids=live_recipe.selected_source_offer_ids,
                    valued_tradeup_results=validated,
                    metrics=metrics,
                    risk_decision=risk_decision,
                )
            )

        return LiveRecipeValuationResult(
            opportunities=tuple(opportunities),
            rejected=tuple(rejected),
        )
    except MemoryError:
        raise
    except Exception:
        raise LiveRecipeValuationError from None


def _validate_complete_valuation(
    value: object,
    original_results: tuple[TradeupResult, ...],
) -> tuple[TradeupResult, ...] | LiveRecipeValuationRejectionReason:
    if type(value) is not ValuationResult:
        return LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT

    lookup = value.price_lookup_result
    if _has_provider_error(lookup, value.warnings):
        return LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    if _has_missing_price(value, lookup, original_results):
        return LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE

    try:
        if type(value.tradeup_results) is not list:
            raise LiveRecipeValuationError
        if not _is_exact_string_list(value.missing_market_hash_names) or (
            value.missing_market_hash_names
        ):
            raise LiveRecipeValuationError
        if not _is_exact_warning_list(value.warnings) or value.warnings:
            raise LiveRecipeValuationError
        if type(lookup) is not PriceLookupResult:
            raise LiveRecipeValuationError
        if type(lookup.quotes) is not dict:
            raise LiveRecipeValuationError
        if not _is_exact_string_list(lookup.missing) or lookup.missing:
            raise LiveRecipeValuationError
        if not _is_exact_string_list(lookup.errors) or lookup.errors:
            raise LiveRecipeValuationError
        if len(value.tradeup_results) != len(original_results):
            raise LiveRecipeValuationError

        expected_names = tuple(
            _validate_nonempty_string(result.output_market_hash_name)
            for result in original_results
        )
        if len(expected_names) != len(set(expected_names)):
            raise LiveRecipeValuationError
        if any(type(key) is not str for key in lookup.quotes):
            raise LiveRecipeValuationError
        if set(lookup.quotes) != set(expected_names):
            raise LiveRecipeValuationError

        valued_results: list[TradeupResult] = []
        for original, candidate in zip(
            original_results,
            value.tradeup_results,
            strict=True,
        ):
            result = _copy_tradeup_result(candidate)
            _validate_geometry_unchanged(original, result)
            quote = lookup.quotes.get(original.output_market_hash_name)
            _validate_aligned_quote(quote, original.output_market_hash_name, result)
            valued_results.append(result)

        total_probability = sum(result.probability for result in valued_results)
        if abs(total_probability - 1.0) > PROBABILITY_TOLERANCE:
            raise LiveRecipeValuationError
        return tuple(valued_results)
    except MemoryError:
        raise
    except Exception:
        return LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT


def _has_provider_error(lookup: object, warnings: object) -> bool:
    if (
        type(lookup) is PriceLookupResult
        and _is_exact_string_list(lookup.errors)
        and bool(lookup.errors)
    ):
        return True
    if type(warnings) is not list or not _is_exact_warning_list(warnings):
        return False
    return any(warning.code == "PRICE_PROVIDER_ERROR" for warning in warnings)


def _has_missing_price(
    value: ValuationResult,
    lookup: object,
    original_results: tuple[TradeupResult, ...],
) -> bool:
    if _is_nonempty_string_list(value.missing_market_hash_names):
        return True
    if type(lookup) is PriceLookupResult and _is_nonempty_string_list(lookup.missing):
        return True
    if _is_exact_warning_list(value.warnings) and any(
        warning.code in _MISSING_WARNING_CODES for warning in value.warnings
    ):
        return True
    if type(lookup) is PriceLookupResult and type(lookup.quotes) is dict:
        return any(
            result.output_market_hash_name not in lookup.quotes
            for result in original_results
        )
    return False


def _is_nonempty_string_list(value: object) -> bool:
    return _is_exact_string_list(value) and bool(value)


def _is_exact_string_list(value: object) -> bool:
    return type(value) is list and all(type(item) is str for item in value)


def _is_exact_warning_list(value: object) -> bool:
    return type(value) is list and all(
        type(warning) is ValuationWarning
        and type(warning.code) is str
        and type(warning.message) is str
        and (
            warning.market_hash_name is None
            or type(warning.market_hash_name) is str
        )
        for warning in value
    )


def _validate_geometry_unchanged(
    original: TradeupResult,
    valued: TradeupResult,
) -> None:
    if (
        valued.output_market_hash_name != original.output_market_hash_name
        or valued.probability != original.probability
        or valued.output_float != original.output_float
        or valued.output_wear != original.output_wear
    ):
        raise LiveRecipeValuationError


def _validate_aligned_quote(
    value: object,
    expected_name: str,
    result: TradeupResult,
) -> None:
    if type(value) is not PriceQuote:
        raise LiveRecipeValuationError
    if type(value.market_hash_name) is not str or value.market_hash_name != expected_name:
        raise LiveRecipeValuationError
    _validate_nonnegative_decimal(value.price_cny)
    _validate_nonempty_string(value.source)
    if result.estimated_price_cny != value.price_cny:
        raise LiveRecipeValuationError


def _build_rejection(
    recipe: LiveConstructedRecipe,
    reason: LiveRecipeValuationRejectionReason,
) -> LiveRecipeValuationRejection:
    return LiveRecipeValuationRejection(
        selected_source_offer_ids=recipe.selected_source_offer_ids,
        reason_code=reason,
    )


def _copy_construction_result(value: object) -> LiveRecipeConstructionResult:
    if type(value) is not LiveRecipeConstructionResult:
        raise LiveRecipeValuationError
    return LiveRecipeConstructionResult(
        classification=value.classification,
        recipes=value.recipes,
    )


def _copy_live_recipe(value: object) -> LiveConstructedRecipe:
    if type(value) is not LiveConstructedRecipe:
        raise LiveRecipeValuationError
    return LiveConstructedRecipe(
        recipe=value.recipe,
        selected_source_offer_ids=value.selected_source_offer_ids,
    )


def _validate_valuation_service(value: object) -> ValuationService:
    if not isinstance(value, ValuationService) or not callable(
        getattr(value, "value_tradeup_results", None)
    ):
        raise LiveRecipeValuationError
    return value


def _copy_solver_config(value: object) -> RecipeSolverConfig:
    if type(value) is not RecipeSolverConfig:
        raise LiveRecipeValuationError
    if type(value.input_rarity) is not str:
        raise LiveRecipeValuationError
    if type(value.input_count) is not int:
        raise LiveRecipeValuationError
    _validate_finite_decimal(value.sell_fee_rate)
    if value.max_candidates_per_collection is not None and type(
        value.max_candidates_per_collection
    ) is not int:
        raise LiveRecipeValuationError
    if value.target_stattrak is not None and type(value.target_stattrak) is not bool:
        raise LiveRecipeValuationError
    if value.target_souvenir is not None and type(value.target_souvenir) is not bool:
        raise LiveRecipeValuationError
    return RecipeSolverConfig(
        input_rarity=str.__str__(value.input_rarity),
        input_count=value.input_count,
        sell_fee_rate=value.sell_fee_rate,
        max_candidates_per_collection=value.max_candidates_per_collection,
        target_stattrak=value.target_stattrak,
        target_souvenir=value.target_souvenir,
    )


def _copy_risk_config(value: object) -> RiskFilterConfig:
    if type(value) is not RiskFilterConfig:
        raise LiveRecipeValuationError
    min_roi = _copy_finite_decimal(value.min_roi)
    min_profit = _copy_finite_decimal(value.min_expected_profit_cny)
    max_loss = _copy_finite_decimal(value.max_worst_case_loss_pct)
    min_probability = _copy_finite_float(value.min_profit_probability)
    max_cost = _copy_finite_decimal(value.max_input_total_cost_cny)
    min_liquidity = _copy_optional_decimal(value.min_liquidity_score)
    if type(value.exclude_souvenir) is not bool or type(value.exclude_stattrak) is not bool:
        raise LiveRecipeValuationError
    excluded_seeds: set[int] | None = None
    if value.exclude_special_pattern_seeds is not None:
        if type(value.exclude_special_pattern_seeds) is not set or any(
            type(seed) is not int for seed in value.exclude_special_pattern_seeds
        ):
            raise LiveRecipeValuationError
        excluded_seeds = set(value.exclude_special_pattern_seeds)
    return RiskFilterConfig(
        min_roi=min_roi,
        min_expected_profit_cny=min_profit,
        max_worst_case_loss_pct=max_loss,
        min_profit_probability=min_probability,
        max_input_total_cost_cny=max_cost,
        min_liquidity_score=min_liquidity,
        exclude_souvenir=value.exclude_souvenir,
        exclude_stattrak=value.exclude_stattrak,
        exclude_special_pattern_seeds=excluded_seeds,
    )


def _copy_complete_valued_results(
    value: object,
    originals: tuple[TradeupResult, ...],
) -> tuple[TradeupResult, ...]:
    if type(value) is not tuple or len(value) != len(originals):
        raise LiveRecipeValuationError
    copied = tuple(_copy_tradeup_result(result) for result in value)
    for original, result in zip(originals, copied, strict=True):
        _validate_geometry_unchanged(original, result)
    total_probability = sum(result.probability for result in copied)
    if abs(total_probability - 1.0) > PROBABILITY_TOLERANCE:
        raise LiveRecipeValuationError
    return copied


def _copy_tradeup_result(value: object) -> TradeupResult:
    if type(value) is not TradeupResult:
        raise LiveRecipeValuationError
    name = _validate_nonempty_string(value.output_market_hash_name)
    probability = _copy_finite_float(value.probability)
    if probability < 0 or probability > 1:
        raise LiveRecipeValuationError
    output_float = _copy_finite_float(value.output_float)
    if output_float < 0 or output_float > 1:
        raise LiveRecipeValuationError
    wear = _validate_nonempty_string(value.output_wear)
    price = _validate_nonnegative_decimal(value.estimated_price_cny)
    contribution = _validate_nonnegative_decimal(value.expected_value_contribution)
    if contribution != price * Decimal(str(probability)):
        raise LiveRecipeValuationError
    return TradeupResult(
        output_market_hash_name=name,
        probability=probability,
        output_float=output_float,
        output_wear=wear,
        estimated_price_cny=price,
        expected_value_contribution=contribution,
    )


def _copy_metrics(value: object) -> OpportunityMetrics:
    if type(value) is not OpportunityMetrics:
        raise LiveRecipeValuationError
    input_cost = _copy_finite_decimal(value.input_total_cost_cny)
    expected_revenue = _copy_finite_decimal(value.expected_revenue_cny)
    expected_profit = _copy_finite_decimal(value.expected_profit_cny)
    roi = _copy_finite_decimal(value.roi)
    worst_profit = _copy_finite_decimal(value.worst_case_profit_cny)
    best_profit = _copy_finite_decimal(value.best_case_profit_cny)
    profit_probability = _copy_probability(value.profit_probability)
    loss_probability = _copy_probability(value.loss_probability)
    break_even_probability = _copy_probability(value.break_even_probability)
    if (
        abs(
            profit_probability + loss_probability + break_even_probability - 1.0
        )
        > PROBABILITY_TOLERANCE
    ):
        raise LiveRecipeValuationError
    return OpportunityMetrics(
        input_total_cost_cny=input_cost,
        expected_revenue_cny=expected_revenue,
        expected_profit_cny=expected_profit,
        roi=roi,
        worst_case_profit_cny=worst_profit,
        best_case_profit_cny=best_profit,
        profit_probability=profit_probability,
        loss_probability=loss_probability,
        break_even_probability=break_even_probability,
    )


def _copy_risk_decision(value: object) -> RiskDecision:
    if type(value) is not RiskDecision:
        raise LiveRecipeValuationError
    if type(value.passed) is not bool:
        raise LiveRecipeValuationError
    if type(value.reasons) is not list or any(
        type(reason) is not str for reason in value.reasons
    ):
        raise LiveRecipeValuationError
    if type(value.reason_codes) is not list or any(
        type(code) is not str for code in value.reason_codes
    ):
        raise LiveRecipeValuationError
    risk_score = _copy_finite_decimal(value.risk_score)
    if risk_score < 0 or risk_score > 100:
        raise LiveRecipeValuationError
    if value.passed != (not value.reason_codes):
        raise LiveRecipeValuationError
    return RiskDecision(
        passed=value.passed,
        reasons=[str.__str__(reason) for reason in value.reasons],
        reason_codes=[str.__str__(code) for code in value.reason_codes],
        risk_score=risk_score,
    )


def _copy_opportunity(value: object) -> LiveValuedOpportunity:
    if type(value) is not LiveValuedOpportunity:
        raise LiveRecipeValuationError
    return LiveValuedOpportunity(
        recipe=value.recipe,
        selected_source_offer_ids=value.selected_source_offer_ids,
        valued_tradeup_results=value.valued_tradeup_results,
        metrics=value.metrics,
        risk_decision=value.risk_decision,
    )


def _copy_rejection(value: object) -> LiveRecipeValuationRejection:
    if type(value) is not LiveRecipeValuationRejection:
        raise LiveRecipeValuationError
    return LiveRecipeValuationRejection(
        selected_source_offer_ids=value.selected_source_offer_ids,
        reason_code=value.reason_code,
    )


def _copy_source_offer_ids(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) != 10:
        raise LiveRecipeValuationError
    copied: list[str] = []
    for source_offer_id in value:
        if type(source_offer_id) is not str:
            raise LiveRecipeValuationError
        if len(source_offer_id) != 64 or any(
            character not in "0123456789abcdef" for character in source_offer_id
        ):
            raise LiveRecipeValuationError
        copied.append(str.__str__(source_offer_id))
    if len(copied) != len(set(copied)):
        raise LiveRecipeValuationError
    return tuple(copied)


def _validate_nonempty_string(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise LiveRecipeValuationError
    return str.__str__(value)


def _copy_probability(value: object) -> float:
    if type(value) is int:
        copied = float(value)
    elif type(value) is float:
        copied = value
    else:
        raise LiveRecipeValuationError
    if not math.isfinite(copied) or copied < 0 or copied > 1:
        raise LiveRecipeValuationError
    return copied


def _copy_finite_float(value: object) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise LiveRecipeValuationError
    return value


def _validate_finite_decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise LiveRecipeValuationError


def _copy_finite_decimal(value: object) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise LiveRecipeValuationError
    return value


def _validate_nonnegative_decimal(value: object) -> Decimal:
    copied = _copy_finite_decimal(value)
    if copied < 0:
        raise LiveRecipeValuationError
    return copied


def _copy_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _copy_finite_decimal(value)
