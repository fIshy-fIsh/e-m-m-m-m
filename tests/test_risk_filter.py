from decimal import Decimal

from app.services.ev_service import OpportunityMetrics
from app.services.risk_filter import (
    EXPECTED_PROFIT_BELOW_MINIMUM,
    INPUT_COST_TOO_HIGH,
    LIQUIDITY_SCORE_MISSING,
    LIQUIDITY_SCORE_TOO_LOW,
    PROFIT_PROBABILITY_BELOW_MINIMUM,
    ROI_BELOW_MINIMUM,
    SOUVENIR_EXCLUDED,
    SPECIAL_PATTERN_SEED_EXCLUDED,
    STATTRAK_EXCLUDED,
    WORST_CASE_LOSS_TOO_HIGH,
    RiskDecision,
    RiskFilterConfig,
    evaluate_opportunity,
)
from app.services.tradeup_engine import InputItem


def _make_input_item(*, souvenir: bool = False, stattrak: bool = False) -> InputItem:
    return InputItem(
        market_hash_name="Input Item",
        collection_name="Collection A",
        rarity="Classified",
        actual_float=0.10,
        min_float=0.00,
        max_float=0.20,
        price_cny=Decimal("10.00"),
        stattrak=stattrak,
        souvenir=souvenir,
    )



def _make_metrics(
    *,
    input_total_cost_cny: str = "100.00",
    expected_revenue_cny: str = "130.00",
    expected_profit_cny: str = "25.00",
    roi: str = "0.25",
    worst_case_profit_cny: str = "-10.00",
    best_case_profit_cny: str = "40.00",
    profit_probability: float = 0.6,
    loss_probability: float = 0.4,
    break_even_probability: float = 0.0,
) -> OpportunityMetrics:
    return OpportunityMetrics(
        input_total_cost_cny=Decimal(input_total_cost_cny),
        expected_revenue_cny=Decimal(expected_revenue_cny),
        expected_profit_cny=Decimal(expected_profit_cny),
        roi=Decimal(roi),
        worst_case_profit_cny=Decimal(worst_case_profit_cny),
        best_case_profit_cny=Decimal(best_case_profit_cny),
        profit_probability=profit_probability,
        loss_probability=loss_probability,
        break_even_probability=break_even_probability,
    )



def _make_config(
    *,
    min_roi: str = "0.05",
    min_expected_profit_cny: str = "20.00",
    max_worst_case_loss_pct: str = "0.25",
    min_profit_probability: float = 0.35,
    max_input_total_cost_cny: str = "1000.00",
    min_liquidity_score: str | None = None,
    exclude_souvenir: bool = False,
    exclude_stattrak: bool = False,
    exclude_special_pattern_seeds: set[int] | None = None,
) -> RiskFilterConfig:
    return RiskFilterConfig(
        min_roi=Decimal(min_roi),
        min_expected_profit_cny=Decimal(min_expected_profit_cny),
        max_worst_case_loss_pct=Decimal(max_worst_case_loss_pct),
        min_profit_probability=min_profit_probability,
        max_input_total_cost_cny=Decimal(max_input_total_cost_cny),
        min_liquidity_score=(
            Decimal(min_liquidity_score) if min_liquidity_score is not None else None
        ),
        exclude_souvenir=exclude_souvenir,
        exclude_stattrak=exclude_stattrak,
        exclude_special_pattern_seeds=exclude_special_pattern_seeds,
    )



def test_evaluate_opportunity_passes_when_all_conditions_pass() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(),
    )

    assert isinstance(decision, RiskDecision)
    assert decision.passed is True
    assert decision.reasons == []
    assert decision.reason_codes == []
    assert decision.risk_score == Decimal("0")



def test_evaluate_opportunity_fails_when_roi_below_minimum() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(roi="0.01"),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(min_roi="0.05"),
    )

    assert decision.passed is False
    assert ROI_BELOW_MINIMUM in decision.reason_codes



def test_evaluate_opportunity_fails_when_expected_profit_below_minimum() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(expected_profit_cny="10.00"),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(min_expected_profit_cny="20.00"),
    )

    assert EXPECTED_PROFIT_BELOW_MINIMUM in decision.reason_codes



def test_evaluate_opportunity_fails_when_worst_case_loss_too_high() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(worst_case_profit_cny="-30.00", input_total_cost_cny="100.00"),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(max_worst_case_loss_pct="0.25"),
    )

    assert WORST_CASE_LOSS_TOO_HIGH in decision.reason_codes



def test_evaluate_opportunity_fails_when_profit_probability_below_minimum() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(profit_probability=0.20),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(min_profit_probability=0.35),
    )

    assert PROFIT_PROBABILITY_BELOW_MINIMUM in decision.reason_codes



def test_evaluate_opportunity_fails_when_input_cost_too_high() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(input_total_cost_cny="1500.00"),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(max_input_total_cost_cny="1000.00"),
    )

    assert INPUT_COST_TOO_HIGH in decision.reason_codes



def test_evaluate_opportunity_fails_when_liquidity_score_missing() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(min_liquidity_score="0.50"),
        liquidity_score=None,
    )

    assert LIQUIDITY_SCORE_MISSING in decision.reason_codes



def test_evaluate_opportunity_fails_when_liquidity_score_too_low() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(min_liquidity_score="0.50"),
        liquidity_score=Decimal("0.40"),
    )

    assert LIQUIDITY_SCORE_TOO_LOW in decision.reason_codes



def test_evaluate_opportunity_fails_when_souvenir_excluded() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item(souvenir=True) for _ in range(10)],
        config=_make_config(exclude_souvenir=True),
    )

    assert SOUVENIR_EXCLUDED in decision.reason_codes



def test_evaluate_opportunity_fails_when_stattrak_excluded() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item(stattrak=True) for _ in range(10)],
        config=_make_config(exclude_stattrak=True),
    )

    assert STATTRAK_EXCLUDED in decision.reason_codes



def test_evaluate_opportunity_fails_when_special_pattern_seed_excluded() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(exclude_special_pattern_seeds={661, 922}),
        paint_seeds=[12, 661],
    )

    assert SPECIAL_PATTERN_SEED_EXCLUDED in decision.reason_codes



def test_evaluate_opportunity_can_return_multiple_failure_reasons() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(
            roi="0.01",
            expected_profit_cny="5.00",
            worst_case_profit_cny="-40.00",
            profit_probability=0.10,
            input_total_cost_cny="1500.00",
        ),
        input_items=[_make_input_item(souvenir=True) for _ in range(10)],
        config=_make_config(
            min_roi="0.05",
            min_expected_profit_cny="20.00",
            max_worst_case_loss_pct="0.25",
            min_profit_probability=0.35,
            max_input_total_cost_cny="1000.00",
            min_liquidity_score="0.50",
            exclude_souvenir=True,
        ),
        liquidity_score=Decimal("0.10"),
    )

    assert decision.passed is False
    assert len(set(decision.reason_codes)) >= 3
    assert decision.risk_score > 0
    assert decision.risk_score <= Decimal("100")



def test_worst_case_profit_non_negative_does_not_trigger_loss_filter() -> None:
    decision = evaluate_opportunity(
        metrics=_make_metrics(worst_case_profit_cny="0.00", input_total_cost_cny="100.00"),
        input_items=[_make_input_item() for _ in range(10)],
        config=_make_config(max_worst_case_loss_pct="0.01"),
    )

    assert WORST_CASE_LOSS_TOO_HIGH not in decision.reason_codes
