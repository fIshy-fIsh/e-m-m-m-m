"""Phase 16C — exact interval-union tests."""

from __future__ import annotations

import math

import pytest

from app.services.float_interval import (
    FloatInterval,
    FloatIntervalUnion,
    FloatIntervalUnionError,
    affine_transform,
    empty_union,
    minkowski_sum_unions,
    single_interval,
)


def test_rejects_nan_inf_and_reversed_bounds() -> None:
    with pytest.raises(FloatIntervalUnionError):
        FloatInterval(lower=math.nan, upper=1.0)
    with pytest.raises(FloatIntervalUnionError):
        FloatInterval(lower=0.0, upper=math.inf)
    with pytest.raises(FloatIntervalUnionError):
        FloatInterval(lower=0.7, upper=0.3)


def test_normalization_merges_overlap() -> None:
    union = FloatIntervalUnion(
        intervals=(
            FloatInterval(lower=0.0, upper=0.4),
            FloatInterval(lower=0.3, upper=0.7),
        )
    )
    assert union.intervals == (
        FloatInterval(lower=0.0, upper=0.7),
    )


def test_touching_merges_when_union_is_continuous() -> None:
    union = FloatIntervalUnion(
        intervals=(
            FloatInterval(
                lower=0.0,
                upper=0.3,
                upper_inclusive=False,
            ),
            FloatInterval(
                lower=0.3,
                upper=0.7,
                lower_inclusive=True,
            ),
        )
    )
    assert len(union.intervals) == 1


def test_touching_stays_separate_when_both_exclude_point() -> None:
    union = FloatIntervalUnion(
        intervals=(
            FloatInterval(
                lower=0.0,
                upper=0.3,
                upper_inclusive=False,
            ),
            FloatInterval(
                lower=0.3,
                upper=0.7,
                lower_inclusive=False,
            ),
        )
    )
    assert len(union.intervals) == 2


def test_gap_preservation_and_intersection() -> None:
    union = FloatIntervalUnion(
        intervals=(
            FloatInterval(lower=0.0, upper=0.2),
            FloatInterval(lower=0.6, upper=0.8),
        )
    )
    middle = single_interval(0.3, 0.5)
    assert union.intersection(middle).is_empty
    overlap = union.intersection(single_interval(0.1, 0.7))
    assert len(overlap.intervals) == 2


def test_exact_minkowski_sum_preserves_gaps() -> None:
    left = FloatIntervalUnion(
        intervals=(
            FloatInterval(lower=0.0, upper=0.1),
            FloatInterval(lower=0.8, upper=0.9),
        )
    )
    right = single_interval(0.0, 0.1)
    summed = minkowski_sum_unions(left, right)
    assert len(summed.intervals) == 2
    assert summed.intervals[0].lower == 0.0
    assert summed.intervals[0].upper == 0.2
    assert summed.intervals[1].lower == 0.8
    assert summed.intervals[1].upper == 1.0


def test_intermediate_sum_can_exceed_one() -> None:
    summed = minkowski_sum_unions(
        single_interval(0.0, 1.0),
        single_interval(0.0, 1.0),
    )
    assert summed.intervals == (
        FloatInterval(lower=0.0, upper=2.0),
    )


def test_affine_transform_and_negative_scale() -> None:
    union = single_interval(0.1, 0.4)
    mapped = affine_transform(union, scale=2.0, shift=0.1)
    assert mapped.intervals[0].lower == pytest.approx(0.3)
    assert mapped.intervals[0].upper == pytest.approx(0.9)
    reversed_union = affine_transform(union, scale=-1.0, shift=1.0)
    assert reversed_union.intervals[0].lower == pytest.approx(0.6)
    assert reversed_union.intervals[0].upper == pytest.approx(0.9)


def test_empty_union_short_circuits_minkowski() -> None:
    assert minkowski_sum_unions(
        empty_union(), single_interval(0.0, 1.0)
    ).is_empty
