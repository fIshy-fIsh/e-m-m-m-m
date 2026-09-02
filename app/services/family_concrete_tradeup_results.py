"""Phase 16E — Finish-level concrete outputs for one recipe family.

The recipe-first path uses Phase 16B structural finish probabilities and the
existing canonical float/wear helpers. It intentionally does not call the
legacy ``calculate_tradeup_results`` wear-row builder.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import cast

from app.services.recipe_family import RecipeFamily, StatTrakMode
from app.services.recipe_family_geometry import RecipeFamilyGeometry
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.tradeup_engine import InputItem, TradeupResult
from app.utils.float_math import (
    FloatInputLike,
    calculate_average_adjusted_float,
    calculate_output_float,
)
from app.utils.wear import get_wear_name

__all__ = (
    "ConcreteFamilyTradeupResults",
    "ConcreteFinishOutcome",
    "FamilyConcreteTradeupResultsError",
    "build_concrete_family_tradeup_results",
)

_PROBABILITY_TOLERANCE = 1e-9
_ZERO = Fraction(0, 1)
_ONE = Fraction(1, 1)


class FamilyConcreteTradeupResultsError(ValueError):
    """Concrete finish-level output construction failed closed."""


@dataclass(frozen=True, kw_only=True, repr=False)
class ConcreteFinishOutcome:
    """One structural finish probability and its concrete output result."""

    finish_key: str
    exact_probability: Fraction
    tradeup_result: TradeupResult

    def __post_init__(self) -> None:
        if (
            type(self.finish_key) is not str
            or len(self.finish_key) != 64
            or any(ch not in "0123456789abcdef" for ch in self.finish_key)
        ):
            raise FamilyConcreteTradeupResultsError(
                "finish_key must be full lowercase SHA-256 hex"
            )
        if type(self.exact_probability) is not Fraction or not (
            _ZERO < self.exact_probability <= _ONE
        ):
            raise FamilyConcreteTradeupResultsError(
                "exact_probability must be a Fraction in (0, 1]"
            )
        if type(self.tradeup_result) is not TradeupResult:
            raise FamilyConcreteTradeupResultsError(
                "tradeup_result must be TradeupResult"
            )
        if self.tradeup_result.probability != float(self.exact_probability):
            raise FamilyConcreteTradeupResultsError(
                "TradeupResult probability must match exact_probability"
            )
        if self.tradeup_result.estimated_price_cny != Decimal("0") or (
            self.tradeup_result.expected_value_contribution != Decimal("0")
        ):
            raise FamilyConcreteTradeupResultsError(
                "pre-valuation result fields must remain zero placeholders"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class ConcreteFamilyTradeupResults:
    """Immutable finish-level concrete outputs for one selected recipe."""

    family_hash: str
    average_adjusted_float: float
    outcomes: tuple[ConcreteFinishOutcome, ...]

    def __post_init__(self) -> None:
        if (
            type(self.family_hash) is not str
            or len(self.family_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in self.family_hash)
        ):
            raise FamilyConcreteTradeupResultsError(
                "family_hash must be full lowercase SHA-256 hex"
            )
        if (
            type(self.average_adjusted_float) is not float
            or not math.isfinite(self.average_adjusted_float)
            or not 0.0 <= self.average_adjusted_float <= 1.0
        ):
            raise FamilyConcreteTradeupResultsError(
                "average_adjusted_float must be finite and in [0, 1]"
            )
        if type(self.outcomes) is not tuple or not self.outcomes or any(
            type(outcome) is not ConcreteFinishOutcome
            for outcome in self.outcomes
        ):
            raise FamilyConcreteTradeupResultsError(
                "outcomes must be a non-empty exact tuple"
            )
        finish_keys = tuple(outcome.finish_key for outcome in self.outcomes)
        if finish_keys != tuple(sorted(finish_keys)) or len(set(finish_keys)) != len(
            finish_keys
        ):
            raise FamilyConcreteTradeupResultsError(
                "finish keys must be unique and sorted"
            )
        names = self.output_market_hash_names
        if len(set(names)) != len(names):
            raise FamilyConcreteTradeupResultsError(
                "concrete output market names must be unique"
            )
        exact_total = sum(
            (outcome.exact_probability for outcome in self.outcomes),
            start=_ZERO,
        )
        if exact_total != _ONE:
            raise FamilyConcreteTradeupResultsError(
                "exact finish probabilities must sum to one"
            )
        float_total = sum(
            outcome.tradeup_result.probability for outcome in self.outcomes
        )
        if abs(float_total - 1.0) > _PROBABILITY_TOLERANCE:
            raise FamilyConcreteTradeupResultsError(
                "float probabilities must sum to one within EV tolerance"
            )

    @property
    def tradeup_results(self) -> tuple[TradeupResult, ...]:
        return tuple(outcome.tradeup_result for outcome in self.outcomes)

    @property
    def output_market_hash_names(self) -> tuple[str, ...]:
        return tuple(
            outcome.tradeup_result.output_market_hash_name
            for outcome in self.outcomes
        )


def build_concrete_family_tradeup_results(
    family: RecipeFamily,
    *,
    geometry: RecipeFamilyGeometry,
    finish_index: StructuralOutputFinishIndex,
    selected_input_items: tuple[InputItem, ...],
) -> ConcreteFamilyTradeupResults:
    """Build exact finish-level outputs from ten concrete family inputs."""

    _validate_authorities(family, geometry, finish_index)
    _validate_selected_inputs(family, selected_input_items)

    average_adjusted = calculate_average_adjusted_float(
        cast(tuple[FloatInputLike, ...], selected_input_items)
    )
    outcomes: list[ConcreteFinishOutcome] = []
    seen_names: set[str] = set()
    represented_collections = {
        name for name, _count in family.collection_counts
    }
    for structural in geometry.outcomes:
        finish = finish_index.by_finish_key(structural.finish_key)
        if finish is None:
            raise FamilyConcreteTradeupResultsError(
                "geometry references an unresolved finish"
            )
        if (
            finish.collection_name not in represented_collections
            or finish.rarity != geometry.output_rarity
            or finish.stattrak is not geometry.output_stattrak
        ):
            raise FamilyConcreteTradeupResultsError(
                "finish does not match family geometry"
            )
        output_float = calculate_output_float(
            avg_adjusted_float=average_adjusted,
            output_min_float=finish.min_float,
            output_max_float=finish.max_float,
        )
        output_wear = get_wear_name(output_float)
        exact_name = finish_index.resolve_wear_market_hash_name(
            finish_key=finish.finish_key,
            wear_name=output_wear,
        )
        if exact_name is None:
            raise FamilyConcreteTradeupResultsError(
                "exact finish+wear market identity is unresolved"
            )
        if exact_name in seen_names:
            raise FamilyConcreteTradeupResultsError(
                "concrete output market identity collision"
            )
        seen_names.add(exact_name)
        outcomes.append(
            ConcreteFinishOutcome(
                finish_key=finish.finish_key,
                exact_probability=structural.probability,
                tradeup_result=TradeupResult(
                    output_market_hash_name=exact_name,
                    probability=float(structural.probability),
                    output_float=output_float,
                    output_wear=output_wear,
                    estimated_price_cny=Decimal("0"),
                    expected_value_contribution=Decimal("0"),
                ),
            )
        )

    outcomes.sort(key=lambda outcome: outcome.finish_key)
    return ConcreteFamilyTradeupResults(
        family_hash=family.family_hash,
        average_adjusted_float=average_adjusted,
        outcomes=tuple(outcomes),
    )


def _validate_authorities(
    family: object,
    geometry: object,
    finish_index: object,
) -> None:
    if type(family) is not RecipeFamily:
        raise FamilyConcreteTradeupResultsError("family must be RecipeFamily")
    if type(geometry) is not RecipeFamilyGeometry:
        raise FamilyConcreteTradeupResultsError(
            "geometry must be RecipeFamilyGeometry"
        )
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise FamilyConcreteTradeupResultsError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    if family.family_hash != geometry.family_hash:
        raise FamilyConcreteTradeupResultsError(
            "family and geometry hashes must match"
        )
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    if geometry.output_stattrak is not expected_stattrak:
        raise FamilyConcreteTradeupResultsError(
            "geometry StatTrak mode must match family"
        )


def _validate_selected_inputs(
    family: RecipeFamily,
    selected_input_items: object,
) -> None:
    if type(selected_input_items) is not tuple or any(
        type(item) is not InputItem for item in selected_input_items
    ):
        raise FamilyConcreteTradeupResultsError(
            "selected_input_items must be tuple[InputItem, ...]"
        )
    if len(selected_input_items) != 10:
        raise FamilyConcreteTradeupResultsError(
            "selected_input_items must contain exactly ten items"
        )
    expected_counts = dict(family.collection_counts)
    actual_counts = Counter(item.collection_name for item in selected_input_items)
    if actual_counts != expected_counts:
        raise FamilyConcreteTradeupResultsError(
            "selected input collection counts must match family exactly"
        )
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    for item in selected_input_items:
        if item.rarity != family.input_rarity:
            raise FamilyConcreteTradeupResultsError(
                "selected input rarity must match family"
            )
        if item.stattrak is not expected_stattrak:
            raise FamilyConcreteTradeupResultsError(
                "selected input StatTrak mode must match family"
            )
        # Souvenir deliberately remains candidate-owned provenance and is not
        # required to be homogeneous for a normal family.
