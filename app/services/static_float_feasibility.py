"""Phase 16C — Exact static float feasibility for RecipeFamily.

This service computes theoretical reachability only. It does not claim
that BUFF has listings, sufficient quantity, attractive prices, or
executable floats. It performs no network I/O and has no production
scanner caller in Phase 16C.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.float_interval import (
    FloatInterval,
    FloatIntervalUnion,
    affine_transform,
    empty_union,
    minkowski_sum_unions,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import get_next_rarity
from app.services.recipe_family import RecipeFamily
from app.services.structural_output_finish import (
    StructuralOutputFinishIndex,
    parse_canonical_wear_name,
)
from app.utils.wear import WEAR_RANGES

__all__ = (
    "InputIdentityFloatEvidence",
    "ReachableOutputWear",
    "StaticFloatFeasibilityError",
    "StaticFloatFeasibilityResult",
    "StaticFloatFeasibilityStatus",
    "build_input_adjusted_interval_unions",
    "build_input_identity_float_evidence",
    "compute_static_float_feasibility",
    "query_target_wear",
)

WEAR_NAME_ORDER: tuple[str, ...] = tuple(WEAR_RANGES.keys())


class StaticFloatFeasibilityStatus(StrEnum):
    FEASIBLE = "feasible"
    NO_ELIGIBLE_INPUT_INTERVAL = "no_eligible_input_interval"
    NO_REACHABLE_OUTPUT_WEAR = "no_reachable_output_wear"
    OUTPUT_WEAR_MAPPING_UNRESOLVED = "output_wear_mapping_unresolved"


class StaticFloatFeasibilityError(ValueError):
    """A static float feasibility input violated the strict contract."""


@dataclass(frozen=True, kw_only=True, repr=False)
class InputIdentityFloatEvidence:
    """Exact pinned input identity with its static adjusted-float interval."""

    market_hash_name: str
    goods_id: str
    collection_name: str
    input_rarity: str
    stattrak: bool
    souvenir: bool
    adjusted_intervals: FloatIntervalUnion

    def __post_init__(self) -> None:
        exact_fields = (
            ("market_hash_name", self.market_hash_name),
            ("goods_id", self.goods_id),
            ("collection_name", self.collection_name),
            ("input_rarity", self.input_rarity),
        )
        for field, value in exact_fields:
            if type(value) is not str or not value or value != value.strip():
                raise StaticFloatFeasibilityError(
                    f"{field} must be an exact non-empty string"
                )
        if type(self.stattrak) is not bool or type(self.souvenir) is not bool:
            raise StaticFloatFeasibilityError(
                "stattrak and souvenir must be booleans"
            )
        if type(self.adjusted_intervals) is not FloatIntervalUnion:
            raise StaticFloatFeasibilityError(
                "adjusted_intervals must be FloatIntervalUnion"
            )
        if self.adjusted_intervals.is_empty:
            raise StaticFloatFeasibilityError(
                "adjusted_intervals cannot be empty"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class ReachableOutputWear:
    finish_key: str
    wear_name: str
    exact_market_hash_name: str
    output_float_intervals: FloatIntervalUnion

    def __post_init__(self) -> None:
        if type(self.finish_key) is not str or not self.finish_key:
            raise StaticFloatFeasibilityError("finish_key must be non-empty")
        if self.wear_name not in WEAR_NAME_ORDER:
            raise StaticFloatFeasibilityError("unsupported wear_name")
        if (
            type(self.exact_market_hash_name) is not str
            or not self.exact_market_hash_name
            or self.exact_market_hash_name != self.exact_market_hash_name.strip()
        ):
            raise StaticFloatFeasibilityError(
                "exact_market_hash_name must be exact and non-empty"
            )
        if type(self.output_float_intervals) is not FloatIntervalUnion:
            raise StaticFloatFeasibilityError(
                "output_float_intervals must be FloatIntervalUnion"
            )
        if self.output_float_intervals.is_empty:
            raise StaticFloatFeasibilityError(
                "output_float_intervals cannot be empty"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class StaticFloatFeasibilityResult:
    family_hash: str
    status: StaticFloatFeasibilityStatus
    reachable_avg_adjusted: FloatIntervalUnion
    reachable_outputs: tuple[ReachableOutputWear, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.family_hash) is not str or len(self.family_hash) != 64:
            raise StaticFloatFeasibilityError("family_hash must be full SHA-256 hex")
        if type(self.status) is not StaticFloatFeasibilityStatus:
            raise StaticFloatFeasibilityError("invalid static feasibility status")
        if type(self.reachable_avg_adjusted) is not FloatIntervalUnion:
            raise StaticFloatFeasibilityError(
                "reachable_avg_adjusted must be FloatIntervalUnion"
            )
        if type(self.reachable_outputs) is not tuple or any(
            type(entry) is not ReachableOutputWear
            for entry in self.reachable_outputs
        ):
            raise StaticFloatFeasibilityError(
                "reachable_outputs must contain exact ReachableOutputWear values"
            )
        if type(self.diagnostics) is not tuple or any(
            type(value) is not str for value in self.diagnostics
        ):
            raise StaticFloatFeasibilityError("diagnostics must be tuple[str, ...]")

    def reachable_wear_names(self) -> tuple[str, ...]:
        """Unique canonical wear names in domain order."""

        present = {entry.wear_name for entry in self.reachable_outputs}
        return tuple(name for name in WEAR_NAME_ORDER if name in present)


def _wear_interval(wear_name: str) -> FloatInterval:
    try:
        lower, upper = WEAR_RANGES[wear_name]
    except KeyError as exc:
        raise StaticFloatFeasibilityError("unsupported canonical wear") from exc
    return FloatInterval(
        lower=float(lower),
        upper=float(upper),
        lower_inclusive=True,
        upper_inclusive=wear_name == "Battle-Scarred",
    )


def _actual_interval_for_skin(skin: SkinMetadata) -> FloatInterval | None:
    wear_name = parse_canonical_wear_name(skin.market_hash_name)
    if wear_name is None:
        raise StaticFloatFeasibilityError(
            "eligible input name lacks exact canonical wear suffix"
        )
    intrinsic = FloatInterval(
        lower=float(skin.min_float),
        upper=float(skin.max_float),
        lower_inclusive=True,
        upper_inclusive=True,
    )
    return intrinsic.intersection(_wear_interval(wear_name))


def _to_adjusted(
    actual: FloatInterval,
    *,
    min_float: float,
    max_float: float,
) -> FloatIntervalUnion:
    width = max_float - min_float
    if not math.isfinite(width) or width <= 0:
        raise StaticFloatFeasibilityError("invalid intrinsic float range")
    return affine_transform(
        FloatIntervalUnion(intervals=(actual,)),
        scale=1.0 / width,
        shift=-min_float / width,
    )


def build_input_identity_float_evidence(
    *,
    skins: tuple[SkinMetadata, ...],
    identity_resolver: BuffCommunityIdentityResolver,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
    represented_collections: tuple[str, ...] | None = None,
) -> tuple[InputIdentityFloatEvidence, ...]:
    """Expose Phase 16C's per-name input interval evidence immutably.

    This uses the same exact identity, stratum, wear intersection, and
    actual-to-adjusted transform as family static feasibility. It adds no
    price or live quantity claim.
    """

    if type(identity_resolver) is not BuffCommunityIdentityResolver:
        raise StaticFloatFeasibilityError(
            "identity_resolver must be BuffCommunityIdentityResolver"
        )
    if type(stattrak_mode) is not StatTrakMode:
        raise StaticFloatFeasibilityError("invalid StatTrak mode")
    represented: frozenset[str] | None = None
    if represented_collections is not None:
        if type(represented_collections) is not tuple or any(
            type(value) is not str or not value or value != value.strip()
            for value in represented_collections
        ):
            raise StaticFloatFeasibilityError(
                "represented_collections must be tuple[exact str, ...]"
            )
        if len(set(represented_collections)) != len(represented_collections):
            raise StaticFloatFeasibilityError(
                "represented_collections must not contain duplicates"
            )
        represented = frozenset(represented_collections)

    goods_by_name = dict(identity_resolver.identities)
    if len(goods_by_name) != len(identity_resolver.identities):
        raise StaticFloatFeasibilityError("pinned identity contains duplicate names")
    expected_stattrak = stattrak_mode is StatTrakMode.STATTRAK
    by_name: dict[str, InputIdentityFloatEvidence] = {}
    for skin in skins:
        if type(skin) is not SkinMetadata:
            raise StaticFloatFeasibilityError("skins must contain SkinMetadata")
        collection_name = skin.collection_name
        if collection_name is None or skin.rarity != input_rarity:
            continue
        if represented is not None and collection_name not in represented:
            continue
        if skin.stattrak is not expected_stattrak:
            continue
        goods_id = goods_by_name.get(skin.market_hash_name)
        if goods_id is None:
            continue
        actual = _actual_interval_for_skin(skin)
        if actual is None:
            continue
        evidence = InputIdentityFloatEvidence(
            market_hash_name=skin.market_hash_name,
            goods_id=goods_id,
            collection_name=collection_name,
            input_rarity=input_rarity,
            stattrak=bool(skin.stattrak),
            souvenir=bool(skin.souvenir),
            adjusted_intervals=_to_adjusted(
                actual,
                min_float=skin.min_float,
                max_float=skin.max_float,
            ),
        )
        existing = by_name.get(evidence.market_hash_name)
        if existing is not None:
            raise StaticFloatFeasibilityError(
                "duplicate exact input identity float evidence"
            )
        by_name[evidence.market_hash_name] = evidence
    return tuple(by_name[name] for name in sorted(by_name))


def build_input_adjusted_interval_unions(
    *,
    skins: tuple[SkinMetadata, ...],
    identity_resolver: BuffCommunityIdentityResolver,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
) -> dict[str, FloatIntervalUnion]:
    """Build exact per-collection adjusted interval unions.

    Normal mode admits exact identity-resolved normal and Souvenir
    non-StatTrak rows. StatTrak mode admits StatTrak rows only.
    """

    evidence = build_input_identity_float_evidence(
        skins=skins,
        identity_resolver=identity_resolver,
        input_rarity=input_rarity,
        stattrak_mode=stattrak_mode,
    )
    pieces: dict[str, list[FloatInterval]] = {}
    for item in evidence:
        pieces.setdefault(item.collection_name, []).extend(
            item.adjusted_intervals.intervals
        )
    return {
        collection_name: FloatIntervalUnion(intervals=tuple(intervals))
        for collection_name, intervals in sorted(pieces.items())
    }


def _n_fold_sum(union: FloatIntervalUnion, count: int) -> FloatIntervalUnion:
    if count < 1 or union.is_empty:
        return empty_union()
    result = union
    for _ in range(count - 1):
        result = minkowski_sum_unions(result, union)
    return result


def _reachable_average(
    family: RecipeFamily,
    by_collection: dict[str, FloatIntervalUnion],
) -> FloatIntervalUnion:
    summed: FloatIntervalUnion | None = None
    for collection_name, count in family.collection_counts:
        union = by_collection.get(collection_name)
        if union is None or union.is_empty:
            return empty_union()
        contribution = _n_fold_sum(union, count)
        summed = (
            contribution
            if summed is None
            else minkowski_sum_unions(summed, contribution)
        )
    if summed is None:
        return empty_union()
    return affine_transform(summed, scale=0.1, shift=0.0)


def compute_static_float_feasibility(
    family: RecipeFamily,
    *,
    skins: tuple[SkinMetadata, ...],
    identity_resolver: BuffCommunityIdentityResolver,
    finish_index: StructuralOutputFinishIndex,
) -> StaticFloatFeasibilityResult:
    """Compute exact theoretical family float/wear reachability."""

    if type(family) is not RecipeFamily:
        raise StaticFloatFeasibilityError("family must be RecipeFamily")
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise StaticFloatFeasibilityError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    by_collection = build_input_adjusted_interval_unions(
        skins=skins,
        identity_resolver=identity_resolver,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
    )
    avg_adjusted = _reachable_average(family, by_collection)
    if avg_adjusted.is_empty:
        missing = tuple(
            collection
            for collection, _count in family.collection_counts
            if collection not in by_collection
        )
        return StaticFloatFeasibilityResult(
            family_hash=family.family_hash,
            status=StaticFloatFeasibilityStatus.NO_ELIGIBLE_INPUT_INTERVAL,
            reachable_avg_adjusted=empty_union(),
            reachable_outputs=(),
            diagnostics=tuple(f"missing_input_interval:{name}" for name in missing),
        )

    output_rarity = get_next_rarity(family.input_rarity)
    if output_rarity is None:
        raise StaticFloatFeasibilityError("family input rarity has no output rarity")
    output_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK

    reachable: list[ReachableOutputWear] = []
    unresolved: list[str] = []
    any_wear = False
    for collection_name, _count in family.collection_counts:
        finish_keys = finish_index.finish_keys_for_collection(
            collection_name=collection_name,
            rarity=output_rarity,
            stattrak=output_stattrak,
        )
        for finish_key in finish_keys:
            finish = finish_index.by_finish_key(finish_key)
            if finish is None:
                raise StaticFloatFeasibilityError("finish index is internally inconsistent")
            output_union = affine_transform(
                avg_adjusted,
                scale=finish.max_float - finish.min_float,
                shift=finish.min_float,
            )
            for wear_name in WEAR_NAME_ORDER:
                overlap = output_union.intersection(
                    FloatIntervalUnion(intervals=(_wear_interval(wear_name),))
                )
                if overlap.is_empty:
                    continue
                any_wear = True
                exact_name = finish_index.resolve_wear_market_hash_name(
                    finish_key=finish_key,
                    wear_name=wear_name,
                )
                if exact_name is None:
                    unresolved.append(f"unresolved_output_wear:{finish_key}:{wear_name}")
                    continue
                reachable.append(
                    ReachableOutputWear(
                        finish_key=finish_key,
                        wear_name=wear_name,
                        exact_market_hash_name=exact_name,
                        output_float_intervals=overlap,
                    )
                )

    if unresolved:
        return StaticFloatFeasibilityResult(
            family_hash=family.family_hash,
            status=StaticFloatFeasibilityStatus.OUTPUT_WEAR_MAPPING_UNRESOLVED,
            reachable_avg_adjusted=avg_adjusted,
            reachable_outputs=(),
            diagnostics=tuple(sorted(unresolved)),
        )
    if not any_wear:
        return StaticFloatFeasibilityResult(
            family_hash=family.family_hash,
            status=StaticFloatFeasibilityStatus.NO_REACHABLE_OUTPUT_WEAR,
            reachable_avg_adjusted=avg_adjusted,
            reachable_outputs=(),
            diagnostics=("no_reachable_output_wear",),
        )
    return StaticFloatFeasibilityResult(
        family_hash=family.family_hash,
        status=StaticFloatFeasibilityStatus.FEASIBLE,
        reachable_avg_adjusted=avg_adjusted,
        reachable_outputs=tuple(
            sorted(
                reachable,
                key=lambda item: (
                    item.finish_key,
                    WEAR_NAME_ORDER.index(item.wear_name),
                ),
            )
        ),
        diagnostics=(),
    )


def query_target_wear(
    result: StaticFloatFeasibilityResult,
    *,
    finish_key: str,
    wear_name: str,
) -> ReachableOutputWear | None:
    """Query an existing result without recomputation."""

    if type(result) is not StaticFloatFeasibilityResult:
        raise StaticFloatFeasibilityError("result must be StaticFloatFeasibilityResult")
    for entry in result.reachable_outputs:
        if entry.finish_key == finish_key and entry.wear_name == wear_name:
            return entry
    return None
