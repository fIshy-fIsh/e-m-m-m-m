"""Phase 16C — Exact float interval-union primitives.

The interval algebra is generic over finite real-valued float bounds:
actual/adjusted/output floats usually live in `[0, 1]`, while an
intermediate sum of ten adjusted values may live in `[0, 10]`.

`FloatIntervalUnion` normalizes to an ordered, non-overlapping tuple.
Overlap is merged. Touching intervals merge only when the union is
continuous at the touching point (at least one side includes it).
No epsilon or tolerance is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = (
    "FloatInterval",
    "FloatIntervalUnion",
    "FloatIntervalUnionError",
    "affine_transform",
    "empty_union",
    "minkowski_sum_unions",
    "single_interval",
)


class FloatIntervalUnionError(ValueError):
    """A float interval input violated the strict contract."""


def _finite_float(value: object, *, field: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise FloatIntervalUnionError(f"{field} must be a finite float")
    return value


@dataclass(frozen=True, kw_only=True, repr=False)
class FloatInterval:
    """One finite interval with explicit open/closed boundaries."""

    lower: float
    upper: float
    lower_inclusive: bool = True
    upper_inclusive: bool = True

    def __post_init__(self) -> None:
        lower = _finite_float(self.lower, field="lower")
        upper = _finite_float(self.upper, field="upper")
        if type(self.lower_inclusive) is not bool:
            raise FloatIntervalUnionError("lower_inclusive must be bool")
        if type(self.upper_inclusive) is not bool:
            raise FloatIntervalUnionError("upper_inclusive must be bool")
        if lower > upper:
            raise FloatIntervalUnionError("lower must be <= upper")

    @property
    def is_empty(self) -> bool:
        return self.lower == self.upper and not (
            self.lower_inclusive and self.upper_inclusive
        )

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def intersection(self, other: FloatInterval) -> FloatInterval | None:
        lower = max(self.lower, other.lower)
        upper = min(self.upper, other.upper)
        if lower > upper:
            return None

        if self.lower > other.lower:
            lower_inclusive = self.lower_inclusive
        elif other.lower > self.lower:
            lower_inclusive = other.lower_inclusive
        else:
            lower_inclusive = self.lower_inclusive and other.lower_inclusive

        if self.upper < other.upper:
            upper_inclusive = self.upper_inclusive
        elif other.upper < self.upper:
            upper_inclusive = other.upper_inclusive
        else:
            upper_inclusive = self.upper_inclusive and other.upper_inclusive

        result = FloatInterval(
            lower=lower,
            upper=upper,
            lower_inclusive=lower_inclusive,
            upper_inclusive=upper_inclusive,
        )
        return None if result.is_empty else result


def _can_merge(left: FloatInterval, right: FloatInterval) -> bool:
    if right.lower < left.upper:
        return True
    if right.lower > left.upper:
        return False
    return left.upper_inclusive or right.lower_inclusive


def _merge(left: FloatInterval, right: FloatInterval) -> FloatInterval:
    if right.upper > left.upper:
        upper = right.upper
        upper_inclusive = right.upper_inclusive
    elif right.upper < left.upper:
        upper = left.upper
        upper_inclusive = left.upper_inclusive
    else:
        upper = left.upper
        upper_inclusive = left.upper_inclusive or right.upper_inclusive
    return FloatInterval(
        lower=left.lower,
        upper=upper,
        lower_inclusive=left.lower_inclusive,
        upper_inclusive=upper_inclusive,
    )


def _normalize(
    intervals: tuple[FloatInterval, ...],
) -> tuple[FloatInterval, ...]:
    ordered = sorted(
        (interval for interval in intervals if not interval.is_empty),
        key=lambda iv: (
            iv.lower,
            not iv.lower_inclusive,
            iv.upper,
            not iv.upper_inclusive,
        ),
    )
    merged: list[FloatInterval] = []
    for interval in ordered:
        if not merged or not _can_merge(merged[-1], interval):
            merged.append(interval)
        else:
            merged[-1] = _merge(merged[-1], interval)
    return tuple(merged)


@dataclass(frozen=True, kw_only=True, repr=False)
class FloatIntervalUnion:
    """Normalized immutable interval union."""

    intervals: tuple[FloatInterval, ...]

    def __post_init__(self) -> None:
        if type(self.intervals) is not tuple:
            raise FloatIntervalUnionError("intervals must be an exact tuple")
        if any(type(interval) is not FloatInterval for interval in self.intervals):
            raise FloatIntervalUnionError(
                "intervals must contain exact FloatInterval values"
            )
        object.__setattr__(self, "intervals", _normalize(self.intervals))

    @property
    def is_empty(self) -> bool:
        return not self.intervals

    def intersection(self, other: FloatIntervalUnion) -> FloatIntervalUnion:
        pieces: list[FloatInterval] = []
        for left in self.intervals:
            for right in other.intervals:
                overlap = left.intersection(right)
                if overlap is not None:
                    pieces.append(overlap)
        return FloatIntervalUnion(intervals=tuple(pieces))


def empty_union() -> FloatIntervalUnion:
    return FloatIntervalUnion(intervals=())


def single_interval(
    lower: float,
    upper: float,
    *,
    lower_inclusive: bool = True,
    upper_inclusive: bool = True,
) -> FloatIntervalUnion:
    return FloatIntervalUnion(
        intervals=(
            FloatInterval(
                lower=lower,
                upper=upper,
                lower_inclusive=lower_inclusive,
                upper_inclusive=upper_inclusive,
            ),
        )
    )


def minkowski_sum_unions(
    left: FloatIntervalUnion,
    right: FloatIntervalUnion,
) -> FloatIntervalUnion:
    """Exact Minkowski sum of two normalized interval unions."""

    if left.is_empty or right.is_empty:
        return empty_union()
    pieces = tuple(
        FloatInterval(
            lower=a.lower + b.lower,
            upper=a.upper + b.upper,
            lower_inclusive=a.lower_inclusive and b.lower_inclusive,
            upper_inclusive=a.upper_inclusive and b.upper_inclusive,
        )
        for a in left.intervals
        for b in right.intervals
    )
    return FloatIntervalUnion(intervals=pieces)


def affine_transform(
    union: FloatIntervalUnion,
    *,
    scale: float,
    shift: float,
) -> FloatIntervalUnion:
    """Apply `y = scale*x + shift` exactly to every interval."""

    scale = _finite_float(scale, field="scale")
    shift = _finite_float(shift, field="shift")
    pieces: list[FloatInterval] = []
    for interval in union.intervals:
        left = scale * interval.lower + shift
        right = scale * interval.upper + shift
        if scale >= 0:
            pieces.append(
                FloatInterval(
                    lower=left,
                    upper=right,
                    lower_inclusive=interval.lower_inclusive,
                    upper_inclusive=interval.upper_inclusive,
                )
            )
        else:
            pieces.append(
                FloatInterval(
                    lower=right,
                    upper=left,
                    lower_inclusive=interval.upper_inclusive,
                    upper_inclusive=interval.lower_inclusive,
                )
            )
    return FloatIntervalUnion(intervals=tuple(pieces))
