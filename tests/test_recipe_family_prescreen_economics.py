"""Phase 16D — Approximate family economics tests."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from app.services.float_interval import single_interval
from app.services.market_universe_builder import StatTrakMode
from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import build_recipe_family
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometry,
    StructuralFinishProbability,
)
from app.services.recipe_family_prescreen_economics import (
    PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF,
    RecipeFamilyPreScreenEconomicsConfig,
    RecipeFamilyPreScreenEconomicsStatus,
    RecipeFamilyPreScreenScenario,
    compute_recipe_family_prescreen_economics,
)
from app.services.static_float_feasibility import (
    InputIdentityFloatEvidence,
    ReachableOutputWear,
    StaticFloatFeasibilityResult,
    StaticFloatFeasibilityStatus,
)
from app.services.steamdt_batch_prescreen import SteamDTBuffPreScreenQuote


def _input(
    name: str,
    *,
    goods_id: str,
    collection: str = "A",
    stattrak: bool = False,
    souvenir: bool = False,
) -> InputIdentityFloatEvidence:
    return InputIdentityFloatEvidence(
        market_hash_name=name,
        goods_id=goods_id,
        collection_name=collection,
        input_rarity="Restricted",
        stattrak=stattrak,
        souvenir=souvenir,
        adjusted_intervals=single_interval(0.0, 1.0),
    )


def _quote(
    name: str,
    price: str,
    *,
    sell_count: int | None = 1,
    update_time: int | str | None = None,
) -> SteamDTBuffPreScreenQuote:
    return SteamDTBuffPreScreenQuote(
        market_hash_name=name,
        sell_price_cny=Decimal(price),
        sell_count=sell_count,
        update_time=update_time,
    )


def _context(
    *,
    counts: tuple[tuple[str, int], ...] = (("A", 10),),
    output_probabilities: tuple[Fraction, ...] = (Fraction(1, 2), Fraction(1, 2)),
    input_names: tuple[tuple[str, str, str], ...] = (
        ("Input A1 (Factory New)", "1", "A"),
        ("Input A2 (Minimal Wear)", "2", "A"),
    ),
    output_names: tuple[str, ...] = (
        "Output X (Factory New)",
        "Output Y (Factory New)",
    ),
    quotes: tuple[SteamDTBuffPreScreenQuote, ...] = (),
):
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=counts,
    )
    outcomes = tuple(
        StructuralFinishProbability(
            finish_key=f"{index + 1:064x}", probability=probability
        )
        for index, probability in enumerate(output_probabilities)
    )
    geometry = RecipeFamilyGeometry(
        family_hash=family.family_hash,
        output_rarity="Classified",
        output_stattrak=False,
        outcomes=outcomes,
    )
    reachable = tuple(
        ReachableOutputWear(
            finish_key=outcome.finish_key,
            wear_name="Factory New",
            exact_market_hash_name=name,
            output_float_intervals=single_interval(0.0, 0.07, upper_inclusive=False),
        )
        for outcome, name in zip(outcomes, output_names, strict=True)
    )
    static = StaticFloatFeasibilityResult(
        family_hash=family.family_hash,
        status=StaticFloatFeasibilityStatus.FEASIBLE,
        reachable_avg_adjusted=single_interval(0.0, 1.0),
        reachable_outputs=reachable,
        diagnostics=(),
    )
    input_evidence = tuple(
        _input(name, goods_id=goods_id, collection=collection)
        for name, goods_id, collection in input_names
    )
    book = PreScreenPriceBook(
        quotes_by_name={quote.market_hash_name: quote for quote in quotes}
    )
    return family, geometry, static, input_evidence, book


def _compute(context):
    family, geometry, static, inputs, book = context
    return compute_recipe_family_prescreen_economics(
        family,
        geometry=geometry,
        static_feasibility=static,
        input_evidence=inputs,
        price_book=book,
        config=RecipeFamilyPreScreenEconomicsConfig(
            sell_fee_rate=Decimal("0.10")
        ),
    )


def _by_label(results):
    return {result.scenario_label: result for result in results}


def test_ax10_two_outputs_produces_exact_three_scenarios() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "2"),
            _quote("Input A2 (Minimal Wear)", "4"),
            _quote("Output X (Factory New)", "50"),
            _quote("Output Y (Factory New)", "30"),
        )
    )
    results = _by_label(_compute(context))
    assert set(results) == set(RecipeFamilyPreScreenScenario)
    optimistic = results[RecipeFamilyPreScreenScenario.OPTIMISTIC]
    base = results[RecipeFamilyPreScreenScenario.BASE]
    conservative = results[RecipeFamilyPreScreenScenario.CONSERVATIVE]
    assert optimistic.estimated_input_cost_cny == Decimal("20")
    assert base.estimated_input_cost_cny == Decimal("30")
    assert conservative.estimated_input_cost_cny == Decimal("40")
    assert optimistic.estimated_gross_output_ev_cny == Decimal("40")
    assert base.estimated_gross_output_ev_cny == Decimal("40")
    assert conservative.estimated_gross_output_ev_cny == Decimal("40")
    assert optimistic.estimated_roi == Fraction(4, 5)
    assert base.estimated_roi == Fraction(1, 5)
    assert conservative.estimated_roi == Fraction(-1, 10)


def test_a6_b4_uses_exact_decimal_fraction_ev_and_sell_fee() -> None:
    context = _context(
        counts=(("A", 6), ("B", 4)),
        output_probabilities=(Fraction(3, 10), Fraction(3, 10), Fraction(4, 10)),
        input_names=(
            ("A Input (Factory New)", "1", "A"),
            ("B Input (Factory New)", "2", "B"),
        ),
        output_names=(
            "A X (Factory New)",
            "A Y (Factory New)",
            "B Z (Factory New)",
        ),
        quotes=(
            _quote("A Input (Factory New)", "2"),
            _quote("B Input (Factory New)", "3"),
            _quote("A X (Factory New)", "10"),
            _quote("A Y (Factory New)", "20"),
            _quote("B Z (Factory New)", "30"),
        ),
    )
    base = _by_label(_compute(context))[RecipeFamilyPreScreenScenario.BASE]
    assert base.estimated_input_cost_cny == Decimal("24")
    assert base.estimated_gross_output_ev_cny == Decimal("21")
    assert base.estimated_net_ev_after_sell_fee_cny == Decimal("18.90")
    assert base.estimated_profit_cny == Decimal("-5.10")
    assert base.estimated_roi == Fraction(-17, 80)


def test_missing_input_collection_quote_is_incomplete() -> None:
    context = _context(
        counts=(("A", 6), ("B", 4)),
        output_probabilities=(Fraction(1, 2), Fraction(1, 2)),
        input_names=(
            ("A Input (Factory New)", "1", "A"),
            ("B Input (Factory New)", "2", "B"),
        ),
        quotes=(
            _quote("A Input (Factory New)", "2"),
            _quote("Output X (Factory New)", "10"),
            _quote("Output Y (Factory New)", "20"),
        ),
    )
    results = _compute(context)
    assert all(
        result.status
        is RecipeFamilyPreScreenEconomicsStatus.MISSING_REQUIRED_INPUT_PRICE
        for result in results
    )
    assert all(result.estimated_roi is None for result in results)


def test_missing_all_reachable_quotes_for_one_finish_is_incomplete() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "2"),
            _quote("Input A2 (Minimal Wear)", "4"),
            _quote("Output X (Factory New)", "10"),
        )
    )
    results = _compute(context)
    assert all(
        result.status
        is RecipeFamilyPreScreenEconomicsStatus.MISSING_REQUIRED_OUTPUT_PRICE
        for result in results
    )


def test_alternative_missing_quote_remains_complete_with_diagnostics() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "2"),
            _quote("Output X (Factory New)", "10"),
            _quote("Output Y (Factory New)", "20"),
        )
    )
    results = _compute(context)
    assert all(
        result.status is RecipeFamilyPreScreenEconomicsStatus.COMPLETE
        for result in results
    )
    assert all(result.alternative_missing_quote_count == 1 for result in results)


def test_even_median_is_exact_decimal_mean_and_timestamp_is_opaque() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "1", update_time="newer?"),
            _quote("Input A2 (Minimal Wear)", "2", update_time=1),
            _quote("Output X (Factory New)", "10"),
            _quote("Output Y (Factory New)", "20"),
        )
    )
    base = _by_label(_compute(context))[RecipeFamilyPreScreenScenario.BASE]
    assert base.estimated_input_cost_cny == Decimal("15.0")
    assert base.estimated_gross_output_ev_cny == Decimal("15")


def test_alternative_wear_prices_do_not_change_structural_probability() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "2"),
            _quote("Output X (Factory New)", "10"),
            _quote("Output Y (Factory New)", "20"),
        )
    )
    family, geometry, static, inputs, book = context
    extra_static = StaticFloatFeasibilityResult(
        family_hash=family.family_hash,
        status=StaticFloatFeasibilityStatus.FEASIBLE,
        reachable_avg_adjusted=static.reachable_avg_adjusted,
        reachable_outputs=(
            *static.reachable_outputs,
            ReachableOutputWear(
                finish_key=geometry.outcomes[0].finish_key,
                wear_name="Minimal Wear",
                exact_market_hash_name="Output X (Minimal Wear)",
                output_float_intervals=single_interval(
                    0.07, 0.15, upper_inclusive=False
                ),
            ),
        ),
        diagnostics=(),
    )
    extra_book = PreScreenPriceBook(
        quotes_by_name={
            **book.quotes_by_name,
            "Output X (Minimal Wear)": _quote(
                "Output X (Minimal Wear)", "100"
            ),
        }
    )
    compute_recipe_family_prescreen_economics(
        family,
        geometry=geometry,
        static_feasibility=extra_static,
        input_evidence=inputs,
        price_book=extra_book,
        config=RecipeFamilyPreScreenEconomicsConfig(
            sell_fee_rate=Decimal("0")
        ),
    )
    assert tuple(outcome.probability for outcome in geometry.outcomes) == (
        Fraction(1, 2),
        Fraction(1, 2),
    )


def test_assumptions_state_no_joint_realizability_proof() -> None:
    context = _context(
        quotes=(
            _quote("Input A1 (Factory New)", "2"),
            _quote("Output X (Factory New)", "10"),
            _quote("Output Y (Factory New)", "20"),
        )
    )
    for result in _compute(context):
        assert (
            PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF
            in result.assumptions
        )
