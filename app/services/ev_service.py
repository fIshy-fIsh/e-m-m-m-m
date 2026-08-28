from dataclasses import dataclass
from decimal import Decimal

from app.services.tradeup_engine import InputItem, TradeupResult

PROBABILITY_TOLERANCE = 1e-9


@dataclass(frozen=True)
class OpportunityMetrics:
    """Aggregated economic metrics for one trade-up opportunity."""

    input_total_cost_cny: Decimal
    expected_revenue_cny: Decimal
    expected_profit_cny: Decimal
    roi: Decimal
    worst_case_profit_cny: Decimal
    best_case_profit_cny: Decimal
    profit_probability: float
    loss_probability: float
    break_even_probability: float



def calculate_opportunity_metrics(
    input_items: list[InputItem],
    tradeup_results: list[TradeupResult],
    sell_fee_rate: Decimal,
) -> OpportunityMetrics:
    """Calculate EV, ROI, and profit distribution metrics for a trade-up opportunity."""

    _validate_inputs(input_items, tradeup_results, sell_fee_rate)

    input_total_cost_cny = _calculate_input_total_cost_cny(input_items)
    fee_multiplier = Decimal("1") - sell_fee_rate
    expected_revenue_cny = _calculate_expected_revenue_cny(tradeup_results)
    expected_profit_cny = expected_revenue_cny * fee_multiplier - input_total_cost_cny
    roi = expected_profit_cny / input_total_cost_cny

    per_result_profits = [
        _build_result_profit_snapshot(result, input_total_cost_cny, fee_multiplier)
        for result in tradeup_results
    ]

    worst_case_profit_cny = min(snapshot.profit_cny for snapshot in per_result_profits)
    best_case_profit_cny = max(snapshot.profit_cny for snapshot in per_result_profits)
    profit_probability = sum(
        snapshot.result.probability for snapshot in per_result_profits if snapshot.profit_cny > 0
    )
    loss_probability = sum(
        snapshot.result.probability for snapshot in per_result_profits if snapshot.profit_cny < 0
    )
    break_even_probability = sum(
        snapshot.result.probability for snapshot in per_result_profits if snapshot.profit_cny == 0
    )

    return OpportunityMetrics(
        input_total_cost_cny=input_total_cost_cny,
        expected_revenue_cny=expected_revenue_cny,
        expected_profit_cny=expected_profit_cny,
        roi=roi,
        worst_case_profit_cny=worst_case_profit_cny,
        best_case_profit_cny=best_case_profit_cny,
        profit_probability=profit_probability,
        loss_probability=loss_probability,
        break_even_probability=break_even_probability,
    )


@dataclass(frozen=True)
class _ResultProfitSnapshot:
    """Internal snapshot of a single output result's net economics."""

    result: TradeupResult
    net_revenue_cny: Decimal
    profit_cny: Decimal



def _validate_inputs(
    input_items: list[InputItem],
    tradeup_results: list[TradeupResult],
    sell_fee_rate: Decimal,
) -> None:
    """Validate EV service inputs before running calculations."""

    if not input_items:
        raise ValueError("input_items cannot be empty")
    if not tradeup_results:
        raise ValueError("tradeup_results cannot be empty")
    if sell_fee_rate < 0:
        raise ValueError("sell_fee_rate cannot be less than 0")
    if sell_fee_rate >= 1:
        raise ValueError("sell_fee_rate must be less than 1")

    input_total_cost_cny = _calculate_input_total_cost_cny(input_items)
    if input_total_cost_cny <= 0:
        raise ValueError("input_total_cost_cny must be greater than 0")

    total_probability = sum(result.probability for result in tradeup_results)
    if abs(total_probability - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError("tradeup_results probabilities must sum to 1")



def _calculate_input_total_cost_cny(input_items: list[InputItem]) -> Decimal:
    """Calculate the total acquisition cost of all trade-up inputs."""

    return sum((item.price_cny for item in input_items), start=Decimal("0"))



def _calculate_expected_revenue_cny(tradeup_results: list[TradeupResult]) -> Decimal:
    """Calculate the gross expected revenue before applying sell fees."""

    return sum(
        (
            result.estimated_price_cny * Decimal(str(result.probability))
            for result in tradeup_results
        ),
        start=Decimal("0"),
    )



def _build_result_profit_snapshot(
    result: TradeupResult,
    input_total_cost_cny: Decimal,
    fee_multiplier: Decimal,
) -> _ResultProfitSnapshot:
    """Build the net revenue and profit snapshot for one trade-up output result."""

    net_revenue_cny = result.estimated_price_cny * fee_multiplier
    profit_cny = net_revenue_cny - input_total_cost_cny
    return _ResultProfitSnapshot(
        result=result,
        net_revenue_cny=net_revenue_cny,
        profit_cny=profit_cny,
    )
