from decimal import Decimal

import pytest

from app.services.tradeup_engine import (
    InputItem,
    OutputCandidate,
    calculate_tradeup_results,
)


def _make_input_item(
    collection_name: str,
    *,
    actual_float: float = 0.10,
    min_float: float = 0.00,
    max_float: float = 0.20,
    rarity: str = "Classified",
    stattrak: bool = False,
    souvenir: bool = False,
) -> InputItem:
    return InputItem(
        market_hash_name=f"{collection_name} Input",
        collection_name=collection_name,
        rarity=rarity,
        actual_float=actual_float,
        min_float=min_float,
        max_float=max_float,
        price_cny=Decimal("10.00"),
        stattrak=stattrak,
        souvenir=souvenir,
    )


def _make_output_candidate(
    market_hash_name: str,
    collection_name: str,
    *,
    min_float: float = 0.00,
    max_float: float = 0.80,
    price: str = "100.00",
) -> OutputCandidate:
    return OutputCandidate(
        market_hash_name=market_hash_name,
        collection_name=collection_name,
        rarity="Covert",
        min_float=min_float,
        max_float=max_float,
        estimated_price_cny=Decimal(price),
    )


def test_single_collection_results_split_probability_evenly() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(10)]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A"),
            _make_output_candidate("A2", "Collection A"),
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert len(results) == 2
    assert results[0].probability == pytest.approx(0.5)
    assert results[1].probability == pytest.approx(0.5)


def test_mixed_collections_assign_expected_probabilities() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(8)] + [
        _make_input_item("Collection B") for _ in range(2)
    ]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A"),
            _make_output_candidate("A2", "Collection A"),
        ],
        "Collection B": [_make_output_candidate("B1", "Collection B")],
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)
    probabilities = {result.output_market_hash_name: result.probability for result in results}

    assert probabilities == pytest.approx({"A1": 0.4, "A2": 0.4, "B1": 0.2})


def test_same_output_is_merged_across_collections() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(5)] + [
        _make_input_item("Collection B") for _ in range(5)
    ]
    output_candidates_by_collection = {
        "Collection A": [_make_output_candidate("Shared Output", "Collection A")],
        "Collection B": [_make_output_candidate("Shared Output", "Collection B")],
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert len(results) == 1
    assert results[0].output_market_hash_name == "Shared Output"
    assert results[0].probability == pytest.approx(1.0)


def test_input_count_must_be_exactly_ten() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(9)]
    output_candidates_by_collection = {
        "Collection A": [_make_output_candidate("A1", "Collection A")]
    }

    with pytest.raises(ValueError, match="exactly 10"):
        calculate_tradeup_results(input_items, output_candidates_by_collection)


def test_rarity_must_be_consistent() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(9)] + [
        _make_input_item("Collection A", rarity="Restricted")
    ]
    output_candidates_by_collection = {
        "Collection A": [_make_output_candidate("A1", "Collection A")]
    }

    with pytest.raises(ValueError, match="same rarity"):
        calculate_tradeup_results(input_items, output_candidates_by_collection)


def test_stattrak_cannot_be_mixed() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(9)] + [
        _make_input_item("Collection A", stattrak=True)
    ]
    output_candidates_by_collection = {
        "Collection A": [_make_output_candidate("A1", "Collection A")]
    }

    with pytest.raises(ValueError, match="stattrak"):
        calculate_tradeup_results(input_items, output_candidates_by_collection)


def test_souvenir_cannot_be_mixed() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(9)] + [
        _make_input_item("Collection A", souvenir=True)
    ]
    output_candidates_by_collection = {
        "Collection A": [_make_output_candidate("A1", "Collection A")]
    }

    with pytest.raises(ValueError, match="souvenir"):
        calculate_tradeup_results(input_items, output_candidates_by_collection)


def test_missing_collection_outputs_raise_error() -> None:
    input_items = [_make_input_item("Collection Missing") for _ in range(10)]

    with pytest.raises(ValueError, match="missing output candidates"):
        calculate_tradeup_results(input_items, {})


def test_empty_output_candidates_raise_error() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(10)]

    with pytest.raises(ValueError, match="cannot be empty"):
        calculate_tradeup_results(input_items, {"Collection A": []})


def test_output_float_is_calculated_correctly() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(10)]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate(
                "A1",
                "Collection A",
                min_float=0.00,
                max_float=0.80,
            )
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert results[0].output_float == pytest.approx(0.4)


def test_output_wear_is_factory_new() -> None:
    input_items = [
        _make_input_item(
            "Collection A",
            actual_float=0.01,
            min_float=0.00,
            max_float=0.20,
        )
        for _ in range(10)
    ]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A", min_float=0.00, max_float=0.10)
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert results[0].output_wear == "Factory New"


def test_output_wear_is_minimal_wear() -> None:
    input_items = [
        _make_input_item(
            "Collection A",
            actual_float=0.10,
            min_float=0.00,
            max_float=0.20,
        )
        for _ in range(10)
    ]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A", min_float=0.00, max_float=0.20)
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert results[0].output_float == pytest.approx(0.10)
    assert results[0].output_wear == "Minimal Wear"


def test_output_wear_is_field_tested() -> None:
    input_items = [
        _make_input_item(
            "Collection A",
            actual_float=0.10,
            min_float=0.00,
            max_float=0.20,
        )
        for _ in range(10)
    ]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A", min_float=0.10, max_float=0.50)
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert results[0].output_float == pytest.approx(0.30)
    assert results[0].output_wear == "Field-Tested"


def test_probability_sum_is_one() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(8)] + [
        _make_input_item("Collection B") for _ in range(2)
    ]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A"),
            _make_output_candidate("A2", "Collection A"),
        ],
        "Collection B": [_make_output_candidate("B1", "Collection B")],
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)

    assert sum(result.probability for result in results) == pytest.approx(1.0)


def test_expected_value_contribution_is_price_times_probability() -> None:
    input_items = [_make_input_item("Collection A") for _ in range(10)]
    output_candidates_by_collection = {
        "Collection A": [
            _make_output_candidate("A1", "Collection A", price="123.45"),
            _make_output_candidate("A2", "Collection A", price="50.00"),
        ]
    }

    results = calculate_tradeup_results(input_items, output_candidates_by_collection)
    result_by_name = {result.output_market_hash_name: result for result in results}

    assert result_by_name["A1"].expected_value_contribution == Decimal("61.725")
    assert result_by_name["A2"].expected_value_contribution == Decimal("25.000")
