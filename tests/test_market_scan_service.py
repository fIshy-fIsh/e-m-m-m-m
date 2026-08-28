from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.clients.buff_client import BuffSellOrder, DryRunBuffClient, MockBuffClient
from app.services.market_scan_service import (
    CandidateListing,
    ScanFilterConfig,
    scan_goods,
    scan_watchlist,
)


def _make_sell_order(
    *,
    goods_id: str = "goods-1",
    listing_id: str = "listing-1",
    price_cny: str = "10.00",
    float_value: float | None = 0.10,
) -> BuffSellOrder:
    return BuffSellOrder(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name="AK-47 | Redline (Field-Tested)",
        price_cny=Decimal(price_cny),
        float_value=float_value,
        paint_seed=123,
        inspect_link="steam://inspect/test",
        seller_id="seller-1",
        raw={"listing_id": listing_id},
    )


class FailingBuffClient:
    async def get_sell_orders(
        self,
        goods_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BuffSellOrder]:
        raise RuntimeError("simulated BUFF failure")

    async def get_goods_info(self, goods_id: str):
        raise NotImplementedError

    async def get_buy_orders(self, goods_id: str):
        raise NotImplementedError

    async def get_price_history(self, goods_id: str):
        raise NotImplementedError



def test_candidate_listing_creates_successfully() -> None:
    candidate = CandidateListing(
        goods_id="goods-1",
        listing_id="listing-1",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        price_cny=Decimal("10.00"),
        float_value=0.10,
        paint_seed=123,
        inspect_link="steam://inspect/test",
        scanned_at=datetime.now(UTC),
        raw={"source": "test"},
    )

    assert candidate.goods_id == "goods-1"



def test_candidate_listing_raises_when_goods_id_empty() -> None:
    with pytest.raises(ValueError, match="goods_id"):
        CandidateListing(
            goods_id="",
            listing_id="listing-1",
            market_hash_name=None,
            price_cny=Decimal("10.00"),
            float_value=0.10,
            paint_seed=None,
            inspect_link=None,
            scanned_at=datetime.now(UTC),
            raw={},
        )



def test_candidate_listing_raises_when_listing_id_empty() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        CandidateListing(
            goods_id="goods-1",
            listing_id="",
            market_hash_name=None,
            price_cny=Decimal("10.00"),
            float_value=0.10,
            paint_seed=None,
            inspect_link=None,
            scanned_at=datetime.now(UTC),
            raw={},
        )



def test_candidate_listing_raises_when_price_negative() -> None:
    with pytest.raises(ValueError, match="price_cny"):
        CandidateListing(
            goods_id="goods-1",
            listing_id="listing-1",
            market_hash_name=None,
            price_cny=Decimal("-1.00"),
            float_value=0.10,
            paint_seed=None,
            inspect_link=None,
            scanned_at=datetime.now(UTC),
            raw={},
        )



def test_candidate_listing_raises_when_float_below_zero() -> None:
    with pytest.raises(ValueError, match="float_value"):
        CandidateListing(
            goods_id="goods-1",
            listing_id="listing-1",
            market_hash_name=None,
            price_cny=Decimal("10.00"),
            float_value=-0.1,
            paint_seed=None,
            inspect_link=None,
            scanned_at=datetime.now(UTC),
            raw={},
        )



def test_candidate_listing_raises_when_float_above_one() -> None:
    with pytest.raises(ValueError, match="float_value"):
        CandidateListing(
            goods_id="goods-1",
            listing_id="listing-1",
            market_hash_name=None,
            price_cny=Decimal("10.00"),
            float_value=1.1,
            paint_seed=None,
            inspect_link=None,
            scanned_at=datetime.now(UTC),
            raw={},
        )



def test_scan_filter_config_creates_successfully() -> None:
    config = ScanFilterConfig(
        max_price_cny=Decimal("20.00"),
        max_float=0.20,
        limit_per_goods=5,
        require_float=True,
    )

    assert config.limit_per_goods == 5



def test_scan_filter_config_raises_when_max_price_negative() -> None:
    with pytest.raises(ValueError, match="max_price_cny"):
        ScanFilterConfig(max_price_cny=Decimal("-1.00"))



def test_scan_filter_config_raises_when_max_float_below_zero() -> None:
    with pytest.raises(ValueError, match="max_float"):
        ScanFilterConfig(max_float=-0.1)



def test_scan_filter_config_raises_when_max_float_above_one() -> None:
    with pytest.raises(ValueError, match="max_float"):
        ScanFilterConfig(max_float=1.1)



def test_scan_filter_config_raises_when_limit_per_goods_not_positive() -> None:
    with pytest.raises(ValueError, match="limit_per_goods"):
        ScanFilterConfig(limit_per_goods=0)



def test_scan_goods_returns_candidate_listings_from_mock_buff_client() -> None:
    client = MockBuffClient(sell_orders_by_goods_id={"goods-1": [_make_sell_order()]})

    result = scan_goods(client, "goods-1")

    assert len(result.candidates) == 1
    assert result.candidates[0].goods_id == "goods-1"



def test_scan_goods_filters_by_max_price_cny() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", price_cny="10.00"),
                _make_sell_order(listing_id="b", price_cny="30.00"),
            ]
        }
    )

    result = scan_goods(client, "goods-1", ScanFilterConfig(max_price_cny=Decimal("20.00")))

    assert [candidate.listing_id for candidate in result.candidates] == ["a"]



def test_scan_goods_filters_by_max_float() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", float_value=0.10),
                _make_sell_order(listing_id="b", float_value=0.30),
                _make_sell_order(listing_id="c", float_value=None),
            ]
        }
    )

    result = scan_goods(client, "goods-1", ScanFilterConfig(max_float=0.20))

    assert [candidate.listing_id for candidate in result.candidates] == ["a"]



def test_scan_goods_require_float_filters_none_float() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", float_value=0.10),
                _make_sell_order(listing_id="b", float_value=None),
            ]
        }
    )

    result = scan_goods(client, "goods-1", ScanFilterConfig(require_float=True))

    assert [candidate.listing_id for candidate in result.candidates] == ["a"]



def test_scan_goods_limit_per_goods_is_applied() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", float_value=0.05),
                _make_sell_order(listing_id="b", float_value=0.10),
                _make_sell_order(listing_id="c", float_value=0.15),
            ]
        }
    )

    result = scan_goods(client, "goods-1", ScanFilterConfig(limit_per_goods=2))

    assert [candidate.listing_id for candidate in result.candidates] == ["a", "b"]



def test_scan_goods_sorts_by_float_low_to_high_and_none_last() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", float_value=None),
                _make_sell_order(listing_id="b", float_value=0.20),
                _make_sell_order(listing_id="c", float_value=0.05),
            ]
        }
    )

    result = scan_goods(client, "goods-1")

    assert [candidate.listing_id for candidate in result.candidates] == ["c", "b", "a"]



def test_scan_goods_sorts_by_price_when_float_equal() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [
                _make_sell_order(listing_id="a", float_value=0.10, price_cny="12.00"),
                _make_sell_order(listing_id="b", float_value=0.10, price_cny="10.00"),
            ]
        }
    )

    result = scan_goods(client, "goods-1")

    assert [candidate.listing_id for candidate in result.candidates] == ["b", "a"]



def test_scan_goods_deduplicates_listing_id() -> None:
    duplicate = _make_sell_order(listing_id="dup", price_cny="10.00")
    duplicate_later = _make_sell_order(listing_id="dup", price_cny="9.00")
    client = MockBuffClient(sell_orders_by_goods_id={"goods-1": [duplicate, duplicate_later]})

    result = scan_goods(client, "goods-1")

    assert len(result.candidates) == 1
    assert result.candidates[0].price_cny == Decimal("10.00")



def test_scan_goods_isolates_buff_client_errors() -> None:
    result = scan_goods(FailingBuffClient(), "goods-1")

    assert result.candidates == []
    assert result.errors
    assert "goods-1" in result.errors[0]



def test_scan_watchlist_merges_results_for_multiple_goods_ids() -> None:
    client = MockBuffClient(
        sell_orders_by_goods_id={
            "goods-1": [_make_sell_order(goods_id="goods-1", listing_id="a")],
            "goods-2": [_make_sell_order(goods_id="goods-2", listing_id="b")],
        }
    )

    result = scan_watchlist(client, ["goods-1", "goods-2"])

    assert [candidate.goods_id for candidate in result.candidates] == ["goods-1", "goods-2"]



def test_scan_watchlist_isolates_single_goods_id_failure() -> None:
    class PartiallyFailingBuffClient(MockBuffClient):
        async def get_sell_orders(self, goods_id: str, page: int = 1, page_size: int = 20):
            if goods_id == "goods-2":
                raise RuntimeError("simulated per-goods failure")
            return await super().get_sell_orders(goods_id, page, page_size)

    client = PartiallyFailingBuffClient(
        sell_orders_by_goods_id={"goods-1": [_make_sell_order(goods_id="goods-1", listing_id="a")]}
    )

    result = scan_watchlist(client, ["goods-1", "goods-2"])

    assert len(result.candidates) == 1
    assert result.candidates[0].goods_id == "goods-1"
    assert result.errors
    assert "goods-2" in result.errors[0]



def test_scan_watchlist_deduplicates_listing_id_globally() -> None:
    duplicate_a = _make_sell_order(goods_id="goods-1", listing_id="dup", price_cny="10.00")
    duplicate_b = _make_sell_order(goods_id="goods-2", listing_id="dup", price_cny="9.00")
    client = MockBuffClient(
        sell_orders_by_goods_id={"goods-1": [duplicate_a], "goods-2": [duplicate_b]}
    )

    result = scan_watchlist(client, ["goods-1", "goods-2"])

    assert len(result.candidates) == 1
    assert result.candidates[0].goods_id == "goods-1"



def test_scan_watchlist_returns_empty_result_for_empty_goods_ids() -> None:
    result = scan_watchlist(MockBuffClient(), [])

    assert result.candidates == []
    assert result.errors == []
    assert result.scanned_goods_ids == []



def test_dry_run_buff_client_scan_returns_empty_candidates() -> None:
    result = scan_watchlist(DryRunBuffClient(), ["goods-1", "goods-2"])

    assert result.candidates == []
    assert result.errors == []
    assert result.scanned_goods_ids == ["goods-1", "goods-2"]
