import pytest

from app.utils.wear import (
    get_max_float_for_wear,
    get_min_float_for_wear,
    get_wear_name,
    is_float_in_wear,
)


@pytest.mark.parametrize(
    ("float_value", "expected_wear"),
    [
        (0.0, "Factory New"),
        (0.069999, "Factory New"),
        (0.07, "Minimal Wear"),
        (0.149999, "Minimal Wear"),
        (0.15, "Field-Tested"),
        (0.379999, "Field-Tested"),
        (0.38, "Well-Worn"),
        (0.449999, "Well-Worn"),
        (0.45, "Battle-Scarred"),
        (1.0, "Battle-Scarred"),
    ],
)
def test_get_wear_name_boundaries(float_value: float, expected_wear: str) -> None:
    assert get_wear_name(float_value) == expected_wear


def test_get_wear_name_raises_when_float_below_zero() -> None:
    with pytest.raises(ValueError, match="float_value"):
        get_wear_name(-0.0001)


def test_get_wear_name_raises_when_float_above_one() -> None:
    with pytest.raises(ValueError, match="float_value"):
        get_wear_name(1.0001)


def test_is_float_in_wear_returns_true_for_matching_band() -> None:
    assert is_float_in_wear(0.10, "Minimal Wear") is True
    assert is_float_in_wear(0.45, "Battle-Scarred") is True


def test_is_float_in_wear_returns_false_for_non_matching_band() -> None:
    assert is_float_in_wear(0.10, "Factory New") is False
    assert is_float_in_wear(0.449999, "Battle-Scarred") is False


def test_is_float_in_wear_raises_when_float_below_zero() -> None:
    with pytest.raises(ValueError, match="float_value"):
        is_float_in_wear(-0.1, "Factory New")


def test_is_float_in_wear_raises_when_float_above_one() -> None:
    with pytest.raises(ValueError, match="float_value"):
        is_float_in_wear(1.1, "Battle-Scarred")


def test_invalid_wear_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unsupported wear name"):
        is_float_in_wear(0.1, "FN")


def test_get_min_float_for_wear_returns_expected_value() -> None:
    assert get_min_float_for_wear("Factory New") == pytest.approx(0.00)
    assert get_min_float_for_wear("Battle-Scarred") == pytest.approx(0.45)


def test_get_max_float_for_wear_returns_expected_value() -> None:
    assert get_max_float_for_wear("Factory New") == pytest.approx(0.07)
    assert get_max_float_for_wear("Battle-Scarred") == pytest.approx(1.00)


def test_get_min_float_for_wear_raises_on_invalid_name() -> None:
    with pytest.raises(ValueError, match="unsupported wear name"):
        get_min_float_for_wear("Invalid Wear")


def test_get_max_float_for_wear_raises_on_invalid_name() -> None:
    with pytest.raises(ValueError, match="unsupported wear name"):
        get_max_float_for_wear("Invalid Wear")
