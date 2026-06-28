from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import cast

from app.utils.float_math import (
    FloatInputLike,
    calculate_average_adjusted_float,
    calculate_output_float,
)
from app.utils.wear import get_wear_name

INPUT_COUNT = 10


@dataclass(frozen=True)
class InputItem:
    """Normalized trade-up input item used by the calculation engine."""

    market_hash_name: str
    collection_name: str
    rarity: str
    actual_float: float
    min_float: float
    max_float: float
    price_cny: Decimal
    stattrak: bool = False
    souvenir: bool = False


@dataclass(frozen=True)
class OutputCandidate:
    """Candidate output item available from a collection trade-up pool."""

    market_hash_name: str
    collection_name: str
    rarity: str
    min_float: float
    max_float: float
    estimated_price_cny: Decimal


@dataclass(frozen=True)
class TradeupResult:
    """Final aggregated result for a possible trade-up output."""

    output_market_hash_name: str
    probability: float
    output_float: float
    output_wear: str
    estimated_price_cny: Decimal
    expected_value_contribution: Decimal


@dataclass(frozen=True)
class _MergedOutputState:
    """Internal accumulator for merging outputs with the same market name."""

    candidate: OutputCandidate
    probability: Fraction



def calculate_tradeup_results(
    input_items: list[InputItem],
    output_candidates_by_collection: dict[str, list[OutputCandidate]],
) -> list[TradeupResult]:
    """Calculate merged trade-up outputs, probabilities, floats, and wear bands."""

    _validate_input_items(input_items, output_candidates_by_collection)

    average_adjusted_float = calculate_average_adjusted_float(
        cast(Iterable[FloatInputLike], input_items)
    )
    merged_outputs: dict[str, _MergedOutputState] = {}
    per_input_weight = Fraction(1, INPUT_COUNT)

    for input_item in input_items:
        output_candidates = output_candidates_by_collection[input_item.collection_name]
        per_output_probability = per_input_weight / len(output_candidates)

        for candidate in output_candidates:
            state = merged_outputs.get(candidate.market_hash_name)
            if state is None:
                merged_outputs[candidate.market_hash_name] = _MergedOutputState(
                    candidate=candidate,
                    probability=per_output_probability,
                )
            else:
                merged_outputs[candidate.market_hash_name] = _MergedOutputState(
                    candidate=state.candidate,
                    probability=state.probability + per_output_probability,
                )

    if sum(state.probability for state in merged_outputs.values()) != Fraction(1, 1):
        raise ValueError("merged probability total must equal 1")

    results = [
        _build_tradeup_result(state, average_adjusted_float)
        for state in merged_outputs.values()
    ]
    return sorted(results, key=lambda result: result.output_market_hash_name)



def _validate_input_items(
    input_items: list[InputItem],
    output_candidates_by_collection: dict[str, list[OutputCandidate]],
) -> None:
    """Validate that trade-up inputs satisfy the simplified V1 engine rules."""

    if len(input_items) != INPUT_COUNT:
        raise ValueError(f"input_items must contain exactly {INPUT_COUNT} items")

    rarities = {item.rarity for item in input_items}
    if len(rarities) != 1:
        raise ValueError("all input_items must have the same rarity")

    stattrak_values = {item.stattrak for item in input_items}
    if len(stattrak_values) != 1:
        raise ValueError("stattrak items cannot be mixed with non-stattrak items")

    souvenir_values = {item.souvenir for item in input_items}
    if len(souvenir_values) != 1:
        raise ValueError("souvenir items cannot be mixed with non-souvenir items")

    for item in input_items:
        if item.collection_name not in output_candidates_by_collection:
            raise ValueError(f"missing output candidates for collection: {item.collection_name}")
        if not output_candidates_by_collection[item.collection_name]:
            raise ValueError(
                f"output candidates cannot be empty for collection: {item.collection_name}"
            )



def _build_tradeup_result(
    state: _MergedOutputState,
    average_adjusted_float: float,
) -> TradeupResult:
    """Build a final trade-up result from a merged output accumulator."""

    candidate = state.candidate
    output_float = calculate_output_float(
        avg_adjusted_float=average_adjusted_float,
        output_min_float=candidate.min_float,
        output_max_float=candidate.max_float,
    )
    output_wear = get_wear_name(output_float)
    probability_decimal = Decimal(state.probability.numerator) / Decimal(
        state.probability.denominator
    )
    expected_value_contribution = candidate.estimated_price_cny * probability_decimal

    return TradeupResult(
        output_market_hash_name=candidate.market_hash_name,
        probability=float(state.probability),
        output_float=output_float,
        output_wear=output_wear,
        estimated_price_cny=candidate.estimated_price_cny,
        expected_value_contribution=expected_value_contribution,
    )
