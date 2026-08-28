from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FloatInputLike(Protocol):
    """Protocol for objects that expose trade-up float input fields."""

    actual_float: float
    min_float: float
    max_float: float


def calculate_adjusted_float(actual_float: float, min_float: float, max_float: float) -> float:
    """Calculate the adjusted float of an input item within its float range.

    The adjusted float normalizes an item's actual float into the [0, 1] interval
    relative to its item-specific min and max float bounds.
    """

    if min_float >= max_float:
        raise ValueError("min_float must be less than max_float")
    if actual_float < min_float:
        raise ValueError("actual_float cannot be less than min_float")
    if actual_float > max_float:
        raise ValueError("actual_float cannot be greater than max_float")

    adjusted_float = (actual_float - min_float) / (max_float - min_float)

    if not 0.0 <= adjusted_float <= 1.0:
        raise ValueError("adjusted_float must be between 0 and 1")

    return adjusted_float


def calculate_average_adjusted_float(inputs: Iterable[dict[str, float] | FloatInputLike]) -> float:
    """Calculate the mean adjusted float across trade-up inputs.

    Each input may be a mapping or a dataclass-like object exposing `actual_float`,
    `min_float`, and `max_float`.
    """

    normalized_inputs = list(inputs)
    if not normalized_inputs:
        raise ValueError("inputs cannot be empty")

    adjusted_floats = [
        calculate_adjusted_float(
            actual_float=_get_input_value(item, "actual_float"),
            min_float=_get_input_value(item, "min_float"),
            max_float=_get_input_value(item, "max_float"),
        )
        for item in normalized_inputs
    ]

    return sum(adjusted_floats) / len(adjusted_floats)


def calculate_output_float(
    avg_adjusted_float: float,
    output_min_float: float,
    output_max_float: float,
) -> float:
    """Map an average adjusted float into an output item's float range."""

    if not 0.0 <= avg_adjusted_float <= 1.0:
        raise ValueError("avg_adjusted_float must be between 0 and 1")
    if output_min_float >= output_max_float:
        raise ValueError("output_min_float must be less than output_max_float")

    return avg_adjusted_float * (output_max_float - output_min_float) + output_min_float


def calculate_tradeup_output_float(
    inputs: Iterable[dict[str, float] | FloatInputLike],
    output_min_float: float,
    output_max_float: float,
) -> float:
    """Calculate the final trade-up output float from normalized input data."""

    average_adjusted_float = calculate_average_adjusted_float(inputs)
    return calculate_output_float(
        avg_adjusted_float=average_adjusted_float,
        output_min_float=output_min_float,
        output_max_float=output_max_float,
    )


def _get_input_value(item: dict[str, float] | FloatInputLike, field_name: str) -> float:
    """Read a required float field from a mapping or dataclass-like object."""

    value: Any
    if isinstance(item, dict):
        value = item[field_name]
    else:
        value = getattr(item, field_name)

    return float(value)
