"""Phase 16D — Targeted BUFF scan planner and decision tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.float_interval import single_interval
from app.services.market_universe_builder import StatTrakMode
from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import build_recipe_family
from app.services.static_float_feasibility import InputIdentityFloatEvidence
from app.services.steamdt_batch_prescreen import SteamDTBuffPreScreenQuote
from app.services.targeted_buff_scan_plan import (
    MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN,
    TargetedBuffScanPlanError,
    build_targeted_buff_input_candidates,
    build_targeted_buff_scan_decision,
    build_targeted_buff_scan_plan,
)


def _family(
    counts: tuple[tuple[str, int], ...],
    *,
    mode: StatTrakMode = StatTrakMode.NORMAL,
):
    return build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=mode,
        collection_counts=counts,
    )


def _evidence(
    collection: str,
    count: int,
    *,
    stattrak: bool = False,
    souvenir_at: int | None = None,
    goods_prefix: str | None = None,
):
    return tuple(
        InputIdentityFloatEvidence(
            market_hash_name=(
                ("StatTrak™ " if stattrak else "")
                + ("Souvenir " if souvenir_at == index else "")
                + f"{collection} Input {index:02d} (Factory New)"
            ),
            goods_id=f"{goods_prefix or collection}-{index:02d}",
            collection_name=collection,
            input_rarity="Restricted",
            stattrak=stattrak,
            souvenir=souvenir_at == index,
            adjusted_intervals=single_interval(index / 100.0, 1.0),
        )
        for index in range(count)
    )


def _book(evidence: tuple[InputIdentityFloatEvidence, ...]) -> PreScreenPriceBook:
    return PreScreenPriceBook(
        quotes_by_name={
            item.market_hash_name: SteamDTBuffPreScreenQuote(
                market_hash_name=item.market_hash_name,
                sell_price_cny=Decimal(index + 1),
                sell_count=100 - index,
                update_time="opaque",
            )
            for index, item in enumerate(evidence)
        }
    )


def _plan(family, evidence, *, priority: int = 1):
    book = _book(evidence)
    candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=evidence,
        price_book=book,
    )
    return build_targeted_buff_scan_plan(
        family,
        candidates=candidates,
        priority=priority,
    )


def _counts(plan):
    result: dict[str, int] = {}
    for item in plan.items:
        result[item.collection_name] = result.get(item.collection_name, 0) + 1
    return result


def test_ax10_enough_candidates_allocates_ten() -> None:
    family = _family((("A", 10),))
    plan = _plan(family, _evidence("A", 12))
    assert plan.hard_request_count == 10
    assert _counts(plan) == {"A": 10}


def test_a6_b4_allocates_six_four() -> None:
    family = _family((("A", 6), ("B", 4)))
    evidence = (*_evidence("A", 6), *_evidence("B", 4))
    plan = _plan(family, evidence)
    assert _counts(plan) == {"A": 6, "B": 4}


def test_a4_b3_c3_allocates_four_three_three() -> None:
    family = _family((("A", 4), ("B", 3), ("C", 3)))
    evidence = (*_evidence("A", 4), *_evidence("B", 3), *_evidence("C", 3))
    plan = _plan(family, evidence)
    assert _counts(plan) == {"A": 4, "B": 3, "C": 3}
    assert tuple(item.collection_role for item in plan.items[:4]) == (
        "primary",
        "primary",
        "primary",
        "primary",
    )


def test_capacity_shortfall_redistributes_to_represented_collection() -> None:
    family = _family((("A", 6), ("B", 4)))
    evidence = (*_evidence("A", 2), *_evidence("B", 12))
    plan = _plan(family, evidence)
    assert _counts(plan) == {"A": 2, "B": 8}
    assert plan.hard_request_count == 10


def test_zero_candidate_represented_collection_is_unbuildable() -> None:
    family = _family((("A", 6), ("B", 4)))
    evidence = _evidence("A", 6)
    with pytest.raises(TargetedBuffScanPlanError):
        _plan(family, evidence)


def test_duplicate_goods_id_collision_fails_closed() -> None:
    family = _family((("A", 6), ("B", 4)))
    evidence = (
        *_evidence("A", 2, goods_prefix="same"),
        *_evidence("B", 2, goods_prefix="same"),
    )
    book = _book(evidence)
    candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=evidence,
        price_book=book,
    )
    with pytest.raises(TargetedBuffScanPlanError):
        build_targeted_buff_scan_plan(family, candidates=candidates, priority=1)


def test_source_order_permutation_produces_same_plan() -> None:
    family = _family((("A", 6), ("B", 4)))
    evidence = (*_evidence("A", 7), *_evidence("B", 5))
    book = _book(evidence)
    first_candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=evidence,
        price_book=book,
    )
    second_candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=tuple(reversed(evidence)),
        price_book=book,
    )
    first = build_targeted_buff_scan_plan(
        family, candidates=first_candidates, priority=1
    )
    second = build_targeted_buff_scan_plan(
        family, candidates=second_candidates, priority=1
    )
    assert first.items == second.items


def test_cap_unique_ids_and_unrelated_collection_never_included() -> None:
    family = _family((("A", 10),))
    evidence = (*_evidence("A", 20), *_evidence("Z", 20))
    plan = _plan(family, evidence)
    assert plan.hard_request_count <= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN
    assert len(set(plan.goods_ids)) == len(plan.goods_ids)
    assert all(item.collection_name == "A" for item in plan.items)


def test_normal_family_may_select_souvenir_without_changing_identity() -> None:
    family = _family((("A", 10),))
    original_hash = family.family_hash
    evidence = _evidence("A", 10, souvenir_at=0)
    plan = _plan(family, evidence)
    assert any(item.market_hash_name.startswith("Souvenir ") for item in plan.items)
    assert family.family_hash == original_hash


def test_stattrak_separation() -> None:
    family = _family((("A", 10),), mode=StatTrakMode.STATTRAK)
    stattrak = _evidence("A", 10, stattrak=True)
    plan = _plan(family, stattrak)
    assert all(item.market_hash_name.startswith("StatTrak™ ") for item in plan.items)
    normal = _evidence("A", 10)
    with pytest.raises(TargetedBuffScanPlanError):
        _plan(family, normal)


def test_candidate_order_price_then_float_then_sell_count_then_identity() -> None:
    family = _family((("A", 10),))
    evidence = _evidence("A", 3)
    quotes = {
        evidence[0].market_hash_name: SteamDTBuffPreScreenQuote(
            market_hash_name=evidence[0].market_hash_name,
            sell_price_cny=Decimal("2"),
            sell_count=100,
            update_time=None,
        ),
        evidence[1].market_hash_name: SteamDTBuffPreScreenQuote(
            market_hash_name=evidence[1].market_hash_name,
            sell_price_cny=Decimal("1"),
            sell_count=None,
            update_time=None,
        ),
        evidence[2].market_hash_name: SteamDTBuffPreScreenQuote(
            market_hash_name=evidence[2].market_hash_name,
            sell_price_cny=Decimal("1"),
            sell_count=999,
            update_time=None,
        ),
    }
    candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=evidence,
        price_book=PreScreenPriceBook(quotes_by_name=quotes),
    )
    assert candidates[0].market_hash_name == evidence[1].market_hash_name
    assert candidates[1].market_hash_name == evidence[2].market_hash_name


def test_decision_one_two_fallback_and_none() -> None:
    family1 = _family((("A", 10),))
    family2 = _family((("B", 10),))
    plan1 = _plan(family1, _evidence("A", 10), priority=1)
    plan2 = _plan(family2, _evidence("B", 10), priority=2)
    key1, key2 = family1.family_key, family2.family_key

    one = build_targeted_buff_scan_decision(
        (key1,), plans_by_family_key={key1: plan1}
    )
    assert one.active_family_key == key1
    assert one.fallback_family_key is None

    two = build_targeted_buff_scan_decision(
        (key1, key2), plans_by_family_key={key1: plan1, key2: plan2}
    )
    assert two.active_family_key == key1
    assert two.fallback_family_key == key2
    assert two.active_plan is plan1

    fallback = build_targeted_buff_scan_decision(
        (key1, key2), plans_by_family_key={key1: None, key2: plan2}
    )
    assert fallback.active_family_key == key2
    assert fallback.fallback_family_key is None
    assert fallback.active_plan is plan2

    none = build_targeted_buff_scan_decision(
        (key1, key2), plans_by_family_key={key1: None, key2: None}
    )
    assert none.active_family_key is None
    assert none.active_plan is None
    assert none.hard_request_cap == 10
    assert len(none.ranked_family_keys) <= 2
