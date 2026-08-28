WEAR_RANGES: dict[str, tuple[float, float]] = {
    "Factory New": (0.00, 0.07),
    "Minimal Wear": (0.07, 0.15),
    "Field-Tested": (0.15, 0.38),
    "Well-Worn": (0.38, 0.45),
    "Battle-Scarred": (0.45, 1.00),
}


def get_wear_name(float_value: float) -> str:
    """Return the CS2 wear name corresponding to a float value."""

    _validate_float_value(float_value)

    if float_value < 0.07:
        return "Factory New"
    if float_value < 0.15:
        return "Minimal Wear"
    if float_value < 0.38:
        return "Field-Tested"
    if float_value < 0.45:
        return "Well-Worn"
    return "Battle-Scarred"


def is_float_in_wear(float_value: float, wear: str) -> bool:
    """Return whether a float value falls within the given wear band."""

    _validate_float_value(float_value)
    min_float, max_float = _get_wear_range(wear)

    if wear == "Battle-Scarred":
        return min_float <= float_value <= max_float

    return min_float <= float_value < max_float


def get_min_float_for_wear(wear: str) -> float:
    """Return the inclusive lower bound for a wear band."""

    min_float, _ = _get_wear_range(wear)
    return min_float


def get_max_float_for_wear(wear: str) -> float:
    """Return the upper bound for a wear band."""

    _, max_float = _get_wear_range(wear)
    return max_float


def _validate_float_value(float_value: float) -> None:
    """Validate that a float value is inside the CS2 global float interval."""

    if not 0.0 <= float_value <= 1.0:
        raise ValueError("float_value must be between 0 and 1")


def _get_wear_range(wear: str) -> tuple[float, float]:
    """Return the configured bounds for a wear name."""

    try:
        return WEAR_RANGES[wear]
    except KeyError as exc:
        raise ValueError(f"unsupported wear name: {wear}") from exc
