"""Phase 16D — Deterministic lexicographic streaming Top-N ranking.

No weighted score, timestamp key, network call, full-universe list, or global
family hash set is used. The state retained for ranked objects is bounded by
``TOP_RANKED_FAMILIES``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Final

from app.services.recipe_family import RecipeFamily
from app.services.recipe_family_prescreen_economics import (
    RecipeFamilyPreScreenEconomics,
    RecipeFamilyPreScreenEconomicsStatus,
    RecipeFamilyPreScreenScenario,
)
from app.services.static_float_feasibility import (
    StaticFloatFeasibilityResult,
    StaticFloatFeasibilityStatus,
)
from app.services.targeted_buff_scan_plan import TargetedBuffScanPlan

__all__ = (
    "TOP_RANKED_FAMILIES",
    "RecipeFamilyPreScreenCandidate",
    "RecipeFamilyRankingError",
    "RecipeFamilyRankingResult",
    "rank_recipe_family_candidates",
)

TOP_RANKED_FAMILIES: Final[int] = 2


class RecipeFamilyRankingError(ValueError):
    """A pre-screen ranking candidate violated the deterministic contract."""


def _hash(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RecipeFamilyRankingError(
            "family_hash must be full lowercase SHA-256 hex"
        )
    return value


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyPreScreenCandidate:
    family: RecipeFamily
    static_feasibility: StaticFloatFeasibilityResult
    economics: tuple[RecipeFamilyPreScreenEconomics, ...]
    targeted_plan: TargetedBuffScanPlan | None
    batch_prescreen_succeeded: bool
    identity_error: bool = False

    def __post_init__(self) -> None:
        if type(self.family) is not RecipeFamily:
            raise RecipeFamilyRankingError("family must be RecipeFamily")
        if type(self.static_feasibility) is not StaticFloatFeasibilityResult:
            raise RecipeFamilyRankingError(
                "static_feasibility must be StaticFloatFeasibilityResult"
            )
        if type(self.economics) is not tuple or any(
            type(value) is not RecipeFamilyPreScreenEconomics
            for value in self.economics
        ):
            raise RecipeFamilyRankingError(
                "economics must contain exact pre-screen economics values"
            )
        labels = tuple(value.scenario_label for value in self.economics)
        if set(labels) != set(RecipeFamilyPreScreenScenario) or len(labels) != 3:
            raise RecipeFamilyRankingError(
                "economics must contain each scenario exactly once"
            )
        family_hash = self.family.family_hash
        if self.static_feasibility.family_hash != family_hash or any(
            value.family_hash != family_hash for value in self.economics
        ):
            raise RecipeFamilyRankingError(
                "candidate components must share exact family_hash"
            )
        if self.targeted_plan is not None:
            if type(self.targeted_plan) is not TargetedBuffScanPlan:
                raise RecipeFamilyRankingError("invalid targeted_plan")
            if self.targeted_plan.family_hash != family_hash:
                raise RecipeFamilyRankingError(
                    "targeted plan family_hash mismatch"
                )
        if type(self.batch_prescreen_succeeded) is not bool:
            raise RecipeFamilyRankingError(
                "batch_prescreen_succeeded must be bool"
            )
        if type(self.identity_error) is not bool:
            raise RecipeFamilyRankingError("identity_error must be bool")

    @property
    def family_hash(self) -> str:
        return self.family.family_hash

    @property
    def family_key(self) -> str:
        return self.family.family_key

    def economics_for(
        self, scenario: RecipeFamilyPreScreenScenario
    ) -> RecipeFamilyPreScreenEconomics:
        return next(
            value for value in self.economics if value.scenario_label is scenario
        )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyRankingResult:
    ranked: tuple[RecipeFamilyPreScreenCandidate, ...]
    candidate_count: int
    excluded_count: int
    exclusion_reason_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.ranked) is not tuple or len(self.ranked) > TOP_RANKED_FAMILIES:
            raise RecipeFamilyRankingError(
                "ranked must be an exact tuple bounded by TOP_RANKED_FAMILIES"
            )
        if any(type(value) is not RecipeFamilyPreScreenCandidate for value in self.ranked):
            raise RecipeFamilyRankingError("ranked contains invalid candidate")
        if type(self.candidate_count) is not int or self.candidate_count < 0:
            raise RecipeFamilyRankingError("candidate_count must be non-negative int")
        if type(self.excluded_count) is not int or self.excluded_count < 0:
            raise RecipeFamilyRankingError("excluded_count must be non-negative int")
        if self.excluded_count > self.candidate_count:
            raise RecipeFamilyRankingError("ranking counters are inconsistent")
        if type(self.exclusion_reason_counts) is not tuple:
            raise RecipeFamilyRankingError(
                "exclusion_reason_counts must be exact tuple"
            )

    @property
    def ranked_family_keys(self) -> tuple[str, ...]:
        return tuple(candidate.family_key for candidate in self.ranked)


def _gate_reasons(candidate: RecipeFamilyPreScreenCandidate) -> tuple[str, ...]:
    reasons: list[str] = []
    static = candidate.static_feasibility
    if static.status is not StaticFloatFeasibilityStatus.FEASIBLE:
        reasons.append("STATIC_FLOAT_INFEASIBLE")
    elif not static.reachable_outputs:
        reasons.append("NO_SUPPORTING_WEAR_BAND")
    if not candidate.batch_prescreen_succeeded:
        reasons.append("BATCH_PRE_SCREEN_FAILED")
    if any(
        value.status is not RecipeFamilyPreScreenEconomicsStatus.COMPLETE
        for value in candidate.economics
    ):
        reasons.append("MISSING_REQUIRED_PRICE")
    if candidate.identity_error:
        reasons.append("UNRESOLVED_IDENTITY")
    if candidate.targeted_plan is None:
        reasons.append("TARGETED_PLAN_UNBUILDABLE")
    elif candidate.targeted_plan.hard_request_count > 10:
        reasons.append("REQUEST_COUNT_OVER_BUDGET")
    elif {
        item.collection_name for item in candidate.targeted_plan.items
    } != {name for name, _count in candidate.family.collection_counts}:
        reasons.append("TARGETED_PLAN_UNBUILDABLE")
    return tuple(reasons)


def _required_metric(value: Fraction | Decimal | None, *, field: str) -> Fraction | Decimal:
    if value is None:
        raise RecipeFamilyRankingError(f"rankable candidate missing {field}")
    return value


def _ranking_key(
    candidate: RecipeFamilyPreScreenCandidate,
) -> tuple[Fraction, Decimal, Fraction, Decimal, int, int, str]:
    base = candidate.economics_for(RecipeFamilyPreScreenScenario.BASE)
    conservative = candidate.economics_for(
        RecipeFamilyPreScreenScenario.CONSERVATIVE
    )
    plan = candidate.targeted_plan
    if plan is None:
        raise RecipeFamilyRankingError("rankable candidate must have targeted plan")
    base_roi = _required_metric(base.estimated_roi, field="base ROI")
    base_profit = _required_metric(base.estimated_profit_cny, field="base profit")
    conservative_roi = _required_metric(
        conservative.estimated_roi,
        field="conservative ROI",
    )
    conservative_profit = _required_metric(
        conservative.estimated_profit_cny,
        field="conservative profit",
    )
    if type(base_roi) is not Fraction or type(conservative_roi) is not Fraction:
        raise RecipeFamilyRankingError("ranking ROI metrics must be Fraction")
    if type(base_profit) is not Decimal or type(conservative_profit) is not Decimal:
        raise RecipeFamilyRankingError("ranking profit metrics must be Decimal")
    return (
        -base_roi,
        -base_profit,
        -conservative_roi,
        -conservative_profit,
        -base.known_sell_count_sum,
        plan.hard_request_count,
        _hash(candidate.family_hash),
    )


def rank_recipe_family_candidates(
    candidates: Iterable[RecipeFamilyPreScreenCandidate],
    *,
    top_n: int = TOP_RANKED_FAMILIES,
) -> RecipeFamilyRankingResult:
    """Stream candidates while retaining at most ``top_n`` ranked objects."""

    if type(top_n) is not int or top_n < 1 or top_n > TOP_RANKED_FAMILIES:
        raise RecipeFamilyRankingError(
            f"top_n must be in [1, {TOP_RANKED_FAMILIES}]"
        )
    retained: list[RecipeFamilyPreScreenCandidate] = []
    candidate_count = 0
    excluded_count = 0
    reason_counts: dict[str, int] = {}
    for candidate in candidates:
        candidate_count += 1
        if type(candidate) is not RecipeFamilyPreScreenCandidate:
            raise RecipeFamilyRankingError(
                "candidate iterable yielded invalid value"
            )
        reasons = _gate_reasons(candidate)
        if reasons:
            excluded_count += 1
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue
        retained.append(candidate)
        retained.sort(key=_ranking_key)
        if len(retained) > top_n:
            retained.pop()
    return RecipeFamilyRankingResult(
        ranked=tuple(retained),
        candidate_count=candidate_count,
        excluded_count=excluded_count,
        exclusion_reason_counts=tuple(sorted(reason_counts.items())),
    )
