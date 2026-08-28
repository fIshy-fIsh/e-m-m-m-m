from decimal import Decimal

import pytest

from app.services.ev_service import OpportunityMetrics, calculate_opportunity_metrics
from app.services.tradeup_engine import InputItem, TradeupResult


def _make_input_item(price_cny: str = "10.00") -> InputItem:
    return InputItem(
        market_hash_name="Input Item",
        collection_name="Collection A",
        rarity="Classified",
        actual_float=0.10,
        min_float=0.00,
        max_float=0.20,
        price_cny=Decimal(price_cny),
        stattrak=False,
        souvenir=False,
    )



def _make_tradeup_result(
    market_hash_name: str,
    *,
    probability: float,
    estimated_price_cny: str,
    output_float: float = 0.10,
    output_wear: str = "Minimal Wear",
) -> TradeupResult:
    return TradeupResult(
        output_market_hash_name=market_hash_name,
        probability=probability,
        output_float=output_float,
        output_wear=output_wear,
        estimated_price_cny=Decimal(estimated_price_cny),
        expected_value_contribution=Decimal("0"),
    )



def test_calculate_opportunity_metrics_normal_case() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=0.5, estimated_price_cny="120.00"),
        _make_tradeup_result("Output B", probability=0.5, estimated_price_cny="80.00"),
    ]

    metrics = calculate_opportunity_metrics(
        input_items=input_items,
        tradeup_results=tradeup_results,
        sell_fee_rate=Decimal("0.025"),
    )

    assert isinstance(metrics, OpportunityMetrics)
    assert metrics.input_total_cost_cny == Decimal("100.00")
    assert metrics.expected_revenue_cny == Decimal("100.000")
    assert metrics.expected_profit_cny == Decimal("-2.500000")
    assert metrics.roi == Decimal("-0.025")



def test_worst_and_best_case_profit_are_correct() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=0.5, estimated_price_cny="120.00"),
        _make_tradeup_result("Output B", probability=0.5, estimated_price_cny="80.00"),
    ]

    metrics = calculate_opportunity_metrics(
        input_items=input_items,
        tradeup_results=tradeup_results,
        sell_fee_rate=Decimal("0.025"),
    )

    assert metrics.worst_case_profit_cny == Decimal("-22.00000")
    assert metrics.best_case_profit_cny == Decimal("17.00000")



def test_profit_and_loss_probability_are_correct() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=0.5, estimated_price_cny="120.00"),
        _make_tradeup_result("Output B", probability=0.5, estimated_price_cny="80.00"),
    ]

    metrics = calculate_opportunity_metrics(
        input_items=input_items,
        tradeup_results=tradeup_results,
        sell_fee_rate=Decimal("0.025"),
    )

    assert metrics.profit_probability == pytest.approx(0.5)
    assert metrics.loss_probability == pytest.approx(0.5)
    assert metrics.break_even_probability == pytest.approx(0.0)



def test_break_even_probability_is_correct() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result(
            "Break Even",
            probability=0.25,
            estimated_price_cny="102.5641025641025641025641026",
        ),
        _make_tradeup_result("Profit", probability=0.25, estimated_price_cny="120.00"),
        _make_tradeup_result("Loss", probability=0.50, estimated_price_cny="80.00"),
    ]

    metrics = calculate_opportunity_metrics(
        input_items=input_items,
        tradeup_results=tradeup_results,
        sell_fee_rate=Decimal("0.025"),
    )

    assert metrics.break_even_probability == pytest.approx(0.25)
    assert metrics.profit_probability == pytest.approx(0.25)
    assert metrics.loss_probability == pytest.approx(0.50)



def test_input_items_cannot_be_empty() -> None:
    tradeup_results = [
        _make_tradeup_result("Output A", probability=1.0, estimated_price_cny="100.00")
    ]

    with pytest.raises(ValueError, match="input_items"):
        calculate_opportunity_metrics([], tradeup_results, Decimal("0.025"))



def test_tradeup_results_cannot_be_empty() -> None:
    input_items = [_make_input_item() for _ in range(10)]

    with pytest.raises(ValueError, match="tradeup_results"):
        calculate_opportunity_metrics(input_items, [], Decimal("0.025"))



def test_input_total_cost_must_be_positive() -> None:
    input_items = [_make_input_item(price_cny="0.00") for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=1.0, estimated_price_cny="100.00")
    ]

    with pytest.raises(ValueError, match="input_total_cost_cny"):
        calculate_opportunity_metrics(input_items, tradeup_results, Decimal("0.025"))



def test_sell_fee_rate_cannot_be_negative() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=1.0, estimated_price_cny="100.00")
    ]

    with pytest.raises(ValueError, match="sell_fee_rate"):
        calculate_opportunity_metrics(input_items, tradeup_results, Decimal("-0.01"))



def test_sell_fee_rate_must_be_less_than_one() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=1.0, estimated_price_cny="100.00")
    ]

    with pytest.raises(ValueError, match="less than 1"):
        calculate_opportunity_metrics(input_items, tradeup_results, Decimal("1"))



def test_probability_sum_must_equal_one() -> None:
    input_items = [_make_input_item() for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=0.4, estimated_price_cny="120.00"),
        _make_tradeup_result("Output B", probability=0.4, estimated_price_cny="80.00"),
    ]

    with pytest.raises(ValueError, match="sum to 1"):
        calculate_opportunity_metrics(input_items, tradeup_results, Decimal("0.025"))



def test_decimal_precision_is_preserved() -> None:
    input_items = [_make_input_item(price_cny="0.10") for _ in range(10)]
    tradeup_results = [
        _make_tradeup_result("Output A", probability=0.5, estimated_price_cny="0.30"),
        _make_tradeup_result("Output B", probability=0.5, estimated_price_cny="0.10"),
    ]

    metrics = calculate_opportunity_metrics(
        input_items=input_items,
        tradeup_results=tradeup_results,
        sell_fee_rate=Decimal("0.00"),
    )

    assert metrics.input_total_cost_cny == Decimal("1.00")
    assert metrics.expected_revenue_cny == Decimal("0.20")
    assert metrics.expected_profit_cny == Decimal("-0.80")
    assert isinstance(metrics.expected_revenue_cny, Decimal)
    assert isinstance(metrics.expected_profit_cny, Decimal)
