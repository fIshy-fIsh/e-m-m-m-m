"""Phase 16D — Deterministic streaming ranking tests."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from app.services.float_interval import single_interval
from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_family import build_recipe_family
from app.services.recipe_family_prescreen_economics import (
    RecipeFamilyPreScreenEconomics,
    RecipeFamilyPreScreenEconomicsStatus,
    RecipeFamilyPreScreenScenario,
)
from app.services.recipe_family_ranking import (
    RecipeFamilyPreScreenCandidate,
    rank_recipe_family_candidates,
)
from app.services.static_float_feasibility import (
    ReachableOutputWear,
    StaticFloatFeasibilityResult,
    StaticFloatFeasibilityStatus,
)
from app.services.targeted_buff_scan_plan import (
    TargetedBuffScanItem,
    TargetedBuffScanPlan,
)


def _family(index: int):
    return build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((f"Collection {index:03d}", 10),),
    )


def _economics(
    family_hash: str,
    *,
    base_roi: Fraction,
    base_profit: Decimal,
    conservative_roi: Fraction,
    conservative_profit: Decimal,
    sell_count: int,
    complete: bool = True,
):
    values = []
    for scenario in RecipeFamilyPreScreenScenario:
        roi = base_roi
        profit = base_profit
        if scenario is RecipeFamilyPreScreenScenario.CONSERVATIVE:
            roi = conservative_roi
            profit = conservative_profit
        status = (
            RecipeFamilyPreScreenEconomicsStatus.COMPLETE
            if complete
            else RecipeFamilyPreScreenEconomicsStatus.MISSING_REQUIRED_INPUT_PRICE
        )
        values.append(
            RecipeFamilyPreScreenEconomics(
                family_hash=family_hash,
                scenario_label=scenario,
                status=status,
                estimated_input_cost_cny=Decimal("10") if complete else None,
                estimated_gross_output_ev_cny=Decimal("20") if complete else None,
                estimated_net_ev_after_sell_fee_cny=(
                    Decimal("20") if complete else None
                ),
                estimated_profit_cny=profit if complete else None,
                estimated_roi=roi if complete else None,
                required_component_missing_count=0 if complete else 1,
                alternative_missing_quote_count=0,
                known_sell_count_sum=sell_count,
                unknown_sell_count_count=0,
                assumptions=("approximate",),
                evidence=("fixture",),
                reason_codes=() if complete else ("MISSING_REQUIRED_PRICE",),
            )
        )
    return tuple(values)


def _candidate(
    index: int,
    *,
    base_roi: Fraction,
    base_profit: str = "10",
    conservative_roi: Fraction = Fraction(0),
    conservative_profit: str = "0",
    sell_count: int = 1,
    request_count: int = 1,
    static_status: StaticFloatFeasibilityStatus = StaticFloatFeasibilityStatus.FEASIBLE,
    batch_ok: bool = True,
    complete: bool = True,
    plan: bool = True,
) -> RecipeFamilyPreScreenCandidate:
    family = _family(index)
    reachable = (
        ReachableOutputWear(
            finish_key="1" * 64,
            wear_name="Factory New",
            exact_market_hash_name="Output (Factory New)",
            output_float_intervals=single_interval(0.0, 0.07, upper_inclusive=False),
        ),
    ) if static_status is StaticFloatFeasibilityStatus.FEASIBLE else ()
    static = StaticFloatFeasibilityResult(
        family_hash=family.family_hash,
        status=static_status,
        reachable_avg_adjusted=(
            single_interval(0.0, 1.0)
            if static_status is StaticFloatFeasibilityStatus.FEASIBLE
            else single_interval(0.0, 0.0)
        ),
        reachable_outputs=reachable,
        diagnostics=(),
    )
    targeted_plan = None
    if plan:
        items = tuple(
            TargetedBuffScanItem(
                market_hash_name=f"Input {index}-{item} (Factory New)",
                goods_id=f"{index}-{item}",
                collection_name=f"Collection {index:03d}",
                collection_role="primary",
                priority_within_collection=item + 1,
            )
            for item in range(request_count)
        )
        targeted_plan = TargetedBuffScanPlan(
            family_hash=family.family_hash,
            items=items,
            stattrak_mode=family.stattrak_mode,
            priority=1,
            hard_request_count=request_count,
            unresolved_identity_count=0,
            diagnostics=("offline",),
        )
    return RecipeFamilyPreScreenCandidate(
        family=family,
        static_feasibility=static,
        economics=_economics(
            family.family_hash,
            base_roi=base_roi,
            base_profit=Decimal(base_profit),
            conservative_roi=conservative_roi,
            conservative_profit=Decimal(conservative_profit),
            sell_count=sell_count,
            complete=complete,
        ),
        targeted_plan=targeted_plan,
        batch_prescreen_succeeded=batch_ok,
    )


def test_streaming_generator_retains_only_top_two() -> None:
    produced = 0

    def candidates():
        nonlocal produced
        for index in range(100):
            produced += 1
            yield _candidate(index, base_roi=Fraction(index, 100))

    result = rank_recipe_family_candidates(candidates())
    assert produced == 100
    assert result.candidate_count == 100
    assert len(result.ranked) == 2
    ranked_rois = [
        candidate.economics_for(
            RecipeFamilyPreScreenScenario.BASE
        ).estimated_roi
        for candidate in result.ranked
    ]
    assert ranked_rois == [
        Fraction(99, 100),
        Fraction(98, 100),
    ]


def test_feed_chunk_boundaries_do_not_change_result() -> None:
    candidates = tuple(
        _candidate(index, base_roi=Fraction(index % 7, 10))
        for index in range(25)
    )
    one_pass = rank_recipe_family_candidates(iter(candidates))

    def chunked():
        for start in range(0, len(candidates), 4):
            yield from candidates[start : start + 4]

    second = rank_recipe_family_candidates(chunked())
    assert one_pass.ranked_family_keys == second.ranked_family_keys


def test_family_hash_is_deterministic_final_tie_break() -> None:
    left = _candidate(1, base_roi=Fraction(1, 2))
    right = _candidate(2, base_roi=Fraction(1, 2))
    result = rank_recipe_family_candidates((right, left))
    assert result.ranked_family_keys == tuple(
        candidate.family_key
        for candidate in sorted((left, right), key=lambda value: value.family_hash)
    )


def test_lexicographic_key_order_is_exact() -> None:
    top_base_roi = _candidate(1, base_roi=Fraction(2, 3), base_profit="1")
    lower_base_roi = _candidate(2, base_roi=Fraction(1, 2), base_profit="1000")
    result = rank_recipe_family_candidates((lower_base_roi, top_base_roi))
    assert result.ranked[0].family_key == top_base_roi.family_key

    higher_profit = _candidate(3, base_roi=Fraction(1, 2), base_profit="2")
    lower_profit = _candidate(4, base_roi=Fraction(1, 2), base_profit="1")
    result = rank_recipe_family_candidates((lower_profit, higher_profit))
    assert result.ranked[0].family_key == higher_profit.family_key


def test_gates_exclude_unrankable_candidates_with_reason_counts() -> None:
    candidates = (
        _candidate(
            1,
            base_roi=Fraction(1),
            static_status=StaticFloatFeasibilityStatus.NO_REACHABLE_OUTPUT_WEAR,
        ),
        _candidate(2, base_roi=Fraction(1), batch_ok=False),
        _candidate(3, base_roi=Fraction(1), complete=False),
        _candidate(4, base_roi=Fraction(1), plan=False),
        _candidate(5, base_roi=Fraction(1, 2)),
    )
    result = rank_recipe_family_candidates(candidates)
    reasons = dict(result.exclusion_reason_counts)
    assert result.excluded_count == 4
    assert reasons["STATIC_FLOAT_INFEASIBLE"] == 1
    assert reasons["BATCH_PRE_SCREEN_FAILED"] == 1
    assert reasons["MISSING_REQUIRED_PRICE"] == 1
    assert reasons["TARGETED_PLAN_UNBUILDABLE"] == 1
    assert result.ranked_family_keys == (candidates[-1].family_key,)
