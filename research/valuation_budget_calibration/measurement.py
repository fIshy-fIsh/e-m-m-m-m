"""Pure exact-name accounting and deterministic empirical quantiles."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, kw_only=True)
class ExactNameMeasurement:
    """Exact-name accounting for one ordered scanner composition result."""

    per_recipe_unique_names: tuple[tuple[str, ...], ...]
    run_unique_names: tuple[str, ...]
    cross_recipe_overlap_count: int
    recipe_2_incremental_new_names: int | None
    reuse_ratio: Fraction

    @property
    def recipe_count(self) -> int:
        return len(self.per_recipe_unique_names)

    @property
    def run_unique_output_names(self) -> int:
        return len(self.run_unique_names)

    @property
    def per_recipe_unique_requested_output_name_counts(self) -> tuple[int, ...]:
        return tuple(len(names) for names in self.per_recipe_unique_names)


@dataclass(frozen=True, kw_only=True)
class QuantileSummary:
    """Seven-point summary using the documented R-7 empirical method."""

    minimum: Fraction
    p25: Fraction
    p50: Fraction
    p75: Fraction
    p90: Fraction
    p95: Fraction
    maximum: Fraction


def measure_output_name_sequences(
    output_name_sequences: Sequence[Sequence[str]],
) -> ExactNameMeasurement:
    """Measure first-seen exact-name demand across ordered recipe sequences."""

    per_recipe = tuple(
        tuple(dict.fromkeys(_validated_names(sequence)))
        for sequence in output_name_sequences
    )
    run_unique = tuple(
        dict.fromkeys(name for names in per_recipe for name in names)
    )
    logical_count = sum(len(names) for names in per_recipe)
    reused_count = logical_count - len(run_unique)
    reuse_ratio = (
        Fraction(reused_count, logical_count)
        if logical_count
        else Fraction(0, 1)
    )
    overlap = 0
    recipe_2_incremental: int | None = None
    if len(per_recipe) >= 2:
        first = set(per_recipe[0])
        second = set(per_recipe[1])
        overlap = len(first & second)
        recipe_2_incremental = len(second - first)
    return ExactNameMeasurement(
        per_recipe_unique_names=per_recipe,
        run_unique_names=run_unique,
        cross_recipe_overlap_count=overlap,
        recipe_2_incremental_new_names=recipe_2_incremental,
        reuse_ratio=reuse_ratio,
    )


def empirical_r7_quantile(values: Sequence[int], probability: Fraction) -> Fraction:
    """Return R-7 quantile: h=(N-1)p, linear between x[floor(h)] and x[ceil(h)]."""

    if not values:
        raise ValueError("quantile values cannot be empty")
    if not Fraction(0, 1) <= probability <= Fraction(1, 1):
        raise ValueError("probability must be in [0, 1]")
    ordered = sorted(_validated_integer(value) for value in values)
    h = Fraction(len(ordered) - 1, 1) * probability
    lower = math.floor(h)
    upper = math.ceil(h)
    fraction = h - lower
    return Fraction(ordered[lower], 1) + fraction * (
        ordered[upper] - ordered[lower]
    )


def summarize_quantiles(values: Sequence[int]) -> QuantileSummary:
    """Return min/P25/P50/P75/P90/P95/max under one R-7 convention."""

    return QuantileSummary(
        minimum=empirical_r7_quantile(values, Fraction(0, 1)),
        p25=empirical_r7_quantile(values, Fraction(1, 4)),
        p50=empirical_r7_quantile(values, Fraction(1, 2)),
        p75=empirical_r7_quantile(values, Fraction(3, 4)),
        p90=empirical_r7_quantile(values, Fraction(9, 10)),
        p95=empirical_r7_quantile(values, Fraction(19, 20)),
        maximum=empirical_r7_quantile(values, Fraction(1, 1)),
    )


def _validated_names(values: Sequence[str]) -> tuple[str, ...]:
    names = tuple(values)
    if any(type(name) is not str or not name for name in names):
        raise ValueError("output names must be non-empty exact strings")
    return names


def _validated_integer(value: int) -> int:
    if type(value) is not int:
        raise TypeError("quantile values must be exact integers")
    return value
