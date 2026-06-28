import asyncio
import json
from pathlib import Path

import pytest

from app.clients.buff_client import BuffSellOrder, DryRunBuffClient, MockBuffClient
from app.services.market_scan_service import ScanFilterConfig
from app.services.metadata_provider import LocalJsonMetadataProvider
from app.services.pipeline_service import EndToEndPipelineConfig, run_mock_pipeline
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig

PIPELINE_METADATA_FIXTURE = Path("tests/fixtures/pipeline/mock_metadata.json")
PIPELINE_ORDERS_FIXTURE = Path("tests/fixtures/pipeline/mock_buff_orders.json")



def _make_pipeline_config(goods_ids: list[str]) -> EndToEndPipelineConfig:
    return EndToEndPipelineConfig(
        goods_ids=goods_ids,
        scan_filter_config=ScanFilterConfig(),
        solver_config=RecipeSolverConfig(
            input_rarity="Restricted",
            input_count=10,
            sell_fee_rate=__import__("decimal").Decimal("0.025"),
        ),
        risk_config=RiskFilterConfig(
            min_roi=__import__("decimal").Decimal("0.05"),
            min_expected_profit_cny=__import__("decimal").Decimal("20.00"),
            max_worst_case_loss_pct=__import__("decimal").Decimal("0.25"),
            min_profit_probability=0.35,
            max_input_total_cost_cny=__import__("decimal").Decimal("1000.00"),
        ),
    )



def _load_mock_orders() -> list[dict[str, object]]:
    return json.loads(PIPELINE_ORDERS_FIXTURE.read_text(encoding="utf-8"))



def _build_mock_buff_client() -> MockBuffClient:
    orders = [
        BuffSellOrder(
            listing_id=str(order["listing_id"]),
            goods_id=str(order["goods_id"]),
            market_hash_name=order["market_hash_name"],
            price_cny=__import__("decimal").Decimal(str(order["price_cny"])),
            float_value=order["float_value"],
            paint_seed=order["paint_seed"],
            inspect_link=order["inspect_link"],
            seller_id=order["seller_id"],
            raw=order["raw"],
        )
        for order in _load_mock_orders()
    ]
    return MockBuffClient(sell_orders_by_goods_id={"goods-1": orders})


class FailingMetadataProvider:
    async def fetch_skins(self):
        raise RuntimeError("metadata failure")



def test_run_mock_pipeline_runs_successfully() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert len(result.scan_result.candidates) >= 10
    assert len(result.recipes) == 1
    assert len(result.recipes[0].input_items) == 10
    assert result.recipes[0].tradeup_results
    assert result.recipes[0].metrics is not None
    assert result.recipes[0].risk_decision is not None
    assert result.errors == []



def test_run_mock_pipeline_with_empty_goods_ids_returns_empty_result() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config([]),
        )
    )

    assert result.scan_result.candidates == []
    assert result.recipes == []


class PartiallyFailingBuffClient(MockBuffClient):
    async def get_sell_orders(self, goods_id: str, page: int = 1, page_size: int = 20):
        if goods_id == "goods-2":
            raise RuntimeError("simulated scan failure")
        return await super().get_sell_orders(goods_id, page, page_size)



def test_run_mock_pipeline_keeps_successful_goods_when_one_scan_fails() -> None:
    seeded_orders = _build_mock_buff_client().sell_orders_by_goods_id["goods-1"]
    client = PartiallyFailingBuffClient(
        sell_orders_by_goods_id={"goods-1": seeded_orders}
    )

    result = asyncio.run(
        run_mock_pipeline(
            buff_client=client,
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1", "goods-2"]),
        )
    )

    assert result.scan_result.candidates
    assert result.errors
    assert "goods-2" in result.errors[0]



def test_run_mock_pipeline_handles_metadata_provider_failure() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=FailingMetadataProvider(),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert result.recipes == []
    assert result.errors
    assert "Metadata provider failed" in result.errors[-1]



def test_run_mock_pipeline_handles_recipe_solver_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import pipeline_service

    def failing_solver(*args, **kwargs):
        raise RuntimeError("solver failure")

    monkeypatch.setattr(pipeline_service, "solve_recipes", failing_solver)

    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert result.recipes == []
    assert result.errors
    assert "Recipe solver failed" in result.errors[-1]



def test_run_mock_pipeline_uses_timezone_aware_timestamps() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=_build_mock_buff_client(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert result.started_at.tzinfo is not None
    assert result.finished_at.tzinfo is not None



def test_run_mock_pipeline_script_module_is_importable() -> None:
    import scripts.run_mock_pipeline as run_mock_pipeline_script

    assert hasattr(run_mock_pipeline_script, "main")



def test_run_mock_pipeline_with_dry_run_client_returns_empty_candidates() -> None:
    result = asyncio.run(
        run_mock_pipeline(
            buff_client=DryRunBuffClient(),
            metadata_provider=LocalJsonMetadataProvider(PIPELINE_METADATA_FIXTURE),
            config=_make_pipeline_config(["goods-1"]),
        )
    )

    assert result.scan_result.candidates == []
    assert result.recipes == []
