from dataclasses import dataclass

import pytest

from app.utils.float_math import (
    calculate_adjusted_float,
    calculate_average_adjusted_float,
    calculate_output_float,
    calculate_tradeup_output_float,
)


@dataclass(frozen=True)
class FloatInput:
    actual_float: float
    min_float: float
    max_float: float


def test_calculate_adjusted_float_normal_case() -> None:
    assert calculate_adjusted_float(0.10, 0.00, 0.20) == pytest.approx(0.5)


def test_calculate_adjusted_float_at_min_float() -> None:
    assert calculate_adjusted_float(0.00, 0.00, 0.20) == pytest.approx(0.0)


def test_calculate_adjusted_float_at_max_float() -> None:
    assert calculate_adjusted_float(0.20, 0.00, 0.20) == pytest.approx(1.0)


def test_calculate_adjusted_float_raises_when_actual_float_below_min() -> None:
    with pytest.raises(ValueError, match="actual_float"):
        calculate_adjusted_float(0.01, 0.02, 0.20)


def test_calculate_adjusted_float_raises_when_actual_float_above_max() -> None:
    with pytest.raises(ValueError, match="actual_float"):
        calculate_adjusted_float(0.21, 0.00, 0.20)


def test_calculate_adjusted_float_raises_when_min_is_not_less_than_max() -> None:
    with pytest.raises(ValueError, match="min_float"):
        calculate_adjusted_float(0.10, 0.20, 0.20)


def test_calculate_average_adjusted_float_with_multiple_dict_inputs() -> None:
    inputs = [
        {"actual_float": 0.00, "min_float": 0.00, "max_float": 0.20},
        {"actual_float": 0.10, "min_float": 0.00, "max_float": 0.20},
        {"actual_float": 0.20, "min_float": 0.00, "max_float": 0.20},
    ]

    assert calculate_average_adjusted_float(inputs) == pytest.approx(0.5)


def test_calculate_average_adjusted_float_with_dataclass_inputs() -> None:
    inputs = [
        FloatInput(actual_float=0.07, min_float=0.07, max_float=0.15),
        FloatInput(actual_float=0.11, min_float=0.07, max_float=0.15),
    ]

    assert calculate_average_adjusted_float(inputs) == pytest.approx(0.25)


def test_calculate_average_adjusted_float_raises_when_inputs_empty() -> None:
    with pytest.raises(ValueError, match="inputs"):
        calculate_average_adjusted_float([])


def test_calculate_output_float_normal_case() -> None:
    assert calculate_output_float(0.5, 0.00, 0.80) == pytest.approx(0.4)


def test_calculate_output_float_raises_when_average_adjusted_float_below_zero() -> None:
    with pytest.raises(ValueError, match="avg_adjusted_float"):
        calculate_output_float(-0.01, 0.00, 0.80)


def test_calculate_output_float_raises_when_average_adjusted_float_above_one() -> None:
    with pytest.raises(ValueError, match="avg_adjusted_float"):
        calculate_output_float(1.01, 0.00, 0.80)


def test_calculate_output_float_raises_when_output_min_is_not_less_than_output_max() -> None:
    with pytest.raises(ValueError, match="output_min_float"):
        calculate_output_float(0.5, 0.20, 0.20)


def test_calculate_tradeup_output_float_combined_flow() -> None:
    inputs = [
        FloatInput(actual_float=0.00, min_float=0.00, max_float=0.20),
        FloatInput(actual_float=0.10, min_float=0.00, max_float=0.20),
        FloatInput(actual_float=0.20, min_float=0.00, max_float=0.20),
    ]

    assert calculate_tradeup_output_float(inputs, 0.00, 0.80) == pytest.approx(0.4)
