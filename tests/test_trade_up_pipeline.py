from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

import app.services.trade_up_pipeline as pipeline_module
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_pipeline import (
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    candidates_to_input_items,
)
from app.services.tradeup_engine import InputItem

NAME = "Synthetic AK-47 | Redline (Field-Tested)"
COLLECTION = "Synthetic Collection"
RARITY = "Restricted"


def _metadata(
    *,
    min_float: float = 0.0,
    max_float: float = 1.0,
) -> TradeUpInputMetadata:
    return TradeUpInputMetadata(
        market_hash_name=NAME,
        collection_name=COLLECTION,
        rarity=RARITY,
        min_float=min_float,
        max_float=max_float,
    )


def _candidate(
    *,
    listing_id: str = "listing-1",
    goods_id: str = "goods-1",
    market_hash_name: str | None = NAME,
    price_cny: Decimal = Decimal("12.34"),
    paintwear: Decimal = Decimal("0.1234"),
) -> TradeUpInputCandidate:
    return TradeUpInputCandidate(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=price_cny,
        paintwear=paintwear,
        asset_id="asset-1",
    )


def test_public_api_is_exact() -> None:
    assert pipeline_module.__all__ == (
        "TradeUpInputMetadata",
        "TradeUpInputMetadataResolver",
        "InMemoryTradeUpInputMetadataResolver",
        "candidates_to_input_items",
        "SyntheticBasketConfig",
        "SyntheticBasket",
        "SyntheticScaleCase",
        "build_synthetic_basket",
        "drive_pipeline_path",
        "drive_enrichment_path",
        "compare_partition_paths",
    )


def test_in_memory_resolver_returns_record_or_none() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver(
        {NAME: _metadata()},
    )
    assert resolver.resolve(NAME) is not None
    assert resolver.resolve("Unknown") is None


def test_adapter_converts_homogeneous_candidates_to_input_items() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(
            listing_id=f"listing-{index}",
            goods_id=f"goods-{index}",
            price_cny=Decimal(f"{10 + index}.00"),
            paintwear=Decimal("0.1"),
        )
        for index in range(10)
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert len(items) == 10
    for index, item in enumerate(items):
        assert isinstance(item, InputItem)
        assert item.market_hash_name == NAME
        assert item.collection_name == COLLECTION
        assert item.rarity == RARITY
        assert item.actual_float == pytest.approx(0.1)
        assert item.min_float == 0.0
        assert item.max_float == 1.0
        assert item.price_cny == Decimal(f"{10 + index}.00")
        assert item.stattrak is False
        assert item.souvenir is False


def test_adapter_skips_candidates_with_unresolved_market_hash_name() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(market_hash_name=NAME),
        _candidate(market_hash_name=None),
        _candidate(market_hash_name=NAME),
        _candidate(market_hash_name=None),
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert len(items) == 2
    assert all(item.market_hash_name == NAME for item in items)


def test_adapter_skips_candidates_with_unknown_market_hash_name() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(market_hash_name=NAME),
        _candidate(market_hash_name="Unknown", goods_id="goods-unknown"),
        _candidate(market_hash_name=NAME),
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert len(items) == 2


def test_adapter_preserves_input_order() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(goods_id="g-1"),
        _candidate(goods_id="g-2"),
        _candidate(goods_id="g-3"),
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert [item.price_cny for item in items] == [
        candidates[0].price_cny,
        candidates[1].price_cny,
        candidates[2].price_cny,
    ]


def test_adapter_returns_empty_list_for_empty_input() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    assert candidates_to_input_items([], resolver) == []


def test_adapter_returns_empty_list_when_all_unresolved() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(market_hash_name=None),
        _candidate(market_hash_name="Unknown", goods_id="g"),
    ]
    assert candidates_to_input_items(candidates, resolver) == []


def test_floating_point_transition_is_explicit_once() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(paintwear=Decimal("0.125000")),
        _candidate(paintwear=Decimal("0.625000")),
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert items[0].actual_float == pytest.approx(0.125)
    assert items[1].actual_float == pytest.approx(0.625)


def test_metadata_supports_collection_min_and_max_float() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver(
        {NAME: _metadata(min_float=0.07, max_float=0.80)}
    )
    items = candidates_to_input_items([_candidate()], resolver)
    assert items[0].min_float == pytest.approx(0.07)
    assert items[0].max_float == pytest.approx(0.80)


def test_full_pipeline_runs_with_synthetic_data() -> None:
    from app.services.ev_service import calculate_opportunity_metrics
    from app.services.recipe_solver import RecipeSolverConfig
    from app.services.risk_filter import RiskFilterConfig, evaluate_opportunity
    from app.services.tradeup_engine import OutputCandidate, calculate_tradeup_results

    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    candidates = [
        _candidate(
            listing_id=f"listing-{index}",
            goods_id=f"goods-{index}",
            price_cny=Decimal(f"{10 + index}.00"),
            paintwear=Decimal("0.1"),
        )
        for index in range(10)
    ]
    items = candidates_to_input_items(candidates, resolver)
    assert len(items) == 10
    expected_cost = sum(c.price_cny for c in candidates)

    output_candidates = {
        COLLECTION: [
            OutputCandidate(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                collection_name=COLLECTION,
                rarity="Classified",
                min_float=0.0,
                max_float=1.0,
                estimated_price_cny=Decimal("50.00"),
            )
        ]
    }
    solver_config = RecipeSolverConfig(
        input_rarity=RARITY,
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        target_stattrak=False,
        target_souvenir=False,
    )
    results = calculate_tradeup_results(items, output_candidates)
    assert len(results) == 1
    assert results[0].output_market_hash_name == (
        "AK-47 | Redline (Field-Tested)"
    )

    metrics = calculate_opportunity_metrics(
        input_items=items,
        tradeup_results=results,
        sell_fee_rate=solver_config.sell_fee_rate,
    )
    assert metrics.input_total_cost_cny == expected_cost

    risk_config = RiskFilterConfig(
        min_roi=Decimal("-1"),
        min_expected_profit_cny=Decimal("-1000"),
        max_worst_case_loss_pct=Decimal("1"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("10000"),
    )
    risk = evaluate_opportunity(
        metrics=metrics,
        input_items=items,
        config=risk_config,
        paint_seeds=None,
    )
    assert isinstance(risk.passed, bool)


def test_module_has_no_live_or_external_dependencies() -> None:
    source = (
        Path(pipeline_module.__file__).read_text(encoding="utf-8").casefold()
    )
    for forbidden in (
        "buff_listing",
        "buff_listing_provider",
        "buff_item_identity",
        "buff_client",
        "steamapis",
        "steamdt",
        "os.environ",
        "open(",
        "json",
        "purchase",
        "scanner",
        "scheduler",
    ):
        assert forbidden not in source
