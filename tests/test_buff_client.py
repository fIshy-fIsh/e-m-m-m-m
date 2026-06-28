import asyncio
from datetime import datetime
from decimal import Decimal

import pytest

from app.clients.buff_client import (
    BuffBuyOrder,
    BuffClientConfig,
    BuffGoodsInfo,
    BuffHttpClient,
    BuffPricePoint,
    BuffSellOrder,
    DryRunBuffClient,
    MockBuffClient,
)


def _make_sell_order() -> BuffSellOrder:
    return BuffSellOrder(
        listing_id="listing-1",
        goods_id="goods-1",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        price_cny=Decimal("88.88"),
        float_value=0.15,
        paint_seed=123,
        inspect_link="steam://inspect/test",
        seller_id="seller-1",
        raw={"source": "test"},
    )



def _make_goods_info() -> BuffGoodsInfo:
    return BuffGoodsInfo(
        goods_id="goods-1",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        localized_name="AK-47 | Redline",
        sell_num=10,
        buy_num=5,
        raw={"source": "test"},
    )



def _make_buy_order() -> BuffBuyOrder:
    return BuffBuyOrder(
        goods_id="goods-1",
        price_cny=Decimal("80.00"),
        quantity=3,
        raw={"source": "test"},
    )



def _make_price_point() -> BuffPricePoint:
    return BuffPricePoint(
        goods_id="goods-1",
        price_cny=Decimal("81.23"),
        timestamp=datetime(2026, 6, 27, 12, 0, 0),
        raw={"source": "test"},
    )



def test_buff_sell_order_creates_successfully() -> None:
    order = _make_sell_order()

    assert order.listing_id == "listing-1"



def test_buff_sell_order_raises_when_listing_id_empty() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        BuffSellOrder(
            listing_id="",
            goods_id="goods-1",
            market_hash_name=None,
            price_cny=Decimal("1"),
            float_value=None,
            paint_seed=None,
            inspect_link=None,
            seller_id=None,
            raw={},
        )



def test_buff_sell_order_raises_when_goods_id_empty() -> None:
    with pytest.raises(ValueError, match="goods_id"):
        BuffSellOrder(
            listing_id="listing-1",
            goods_id="",
            market_hash_name=None,
            price_cny=Decimal("1"),
            float_value=None,
            paint_seed=None,
            inspect_link=None,
            seller_id=None,
            raw={},
        )



def test_buff_sell_order_raises_when_price_negative() -> None:
    with pytest.raises(ValueError, match="price_cny"):
        BuffSellOrder(
            listing_id="listing-1",
            goods_id="goods-1",
            market_hash_name=None,
            price_cny=Decimal("-1"),
            float_value=None,
            paint_seed=None,
            inspect_link=None,
            seller_id=None,
            raw={},
        )



def test_buff_sell_order_raises_when_float_below_zero() -> None:
    with pytest.raises(ValueError, match="float_value"):
        BuffSellOrder(
            listing_id="listing-1",
            goods_id="goods-1",
            market_hash_name=None,
            price_cny=Decimal("1"),
            float_value=-0.1,
            paint_seed=None,
            inspect_link=None,
            seller_id=None,
            raw={},
        )



def test_buff_sell_order_raises_when_float_above_one() -> None:
    with pytest.raises(ValueError, match="float_value"):
        BuffSellOrder(
            listing_id="listing-1",
            goods_id="goods-1",
            market_hash_name=None,
            price_cny=Decimal("1"),
            float_value=1.1,
            paint_seed=None,
            inspect_link=None,
            seller_id=None,
            raw={},
        )



def test_buff_goods_info_creates_successfully() -> None:
    info = _make_goods_info()

    assert info.market_hash_name == "AK-47 | Redline (Field-Tested)"



def test_buff_goods_info_raises_when_goods_id_empty() -> None:
    with pytest.raises(ValueError, match="goods_id"):
        BuffGoodsInfo(
            goods_id="",
            market_hash_name="Valid Name",
            localized_name=None,
            sell_num=None,
            buy_num=None,
            raw={},
        )



def test_buff_goods_info_raises_when_market_hash_name_empty() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        BuffGoodsInfo(
            goods_id="goods-1",
            market_hash_name="",
            localized_name=None,
            sell_num=None,
            buy_num=None,
            raw={},
        )



def test_mock_buff_client_returns_preseeded_sell_orders() -> None:
    order = _make_sell_order()
    client = MockBuffClient(sell_orders_by_goods_id={"goods-1": [order]})

    result = asyncio.run(client.get_sell_orders("goods-1"))

    assert result == [order]



def test_mock_buff_client_returns_preseeded_goods_info() -> None:
    info = _make_goods_info()
    client = MockBuffClient(goods_info_by_goods_id={"goods-1": info})

    result = asyncio.run(client.get_goods_info("goods-1"))

    assert result == info



def test_mock_buff_client_returns_preseeded_buy_orders_or_empty_list() -> None:
    order = _make_buy_order()
    client = MockBuffClient(buy_orders_by_goods_id={"goods-1": [order]})

    assert asyncio.run(client.get_buy_orders("goods-1")) == [order]
    assert asyncio.run(client.get_buy_orders("goods-2")) == []



def test_mock_buff_client_returns_preseeded_price_history_or_empty_list() -> None:
    point = _make_price_point()
    client = MockBuffClient(price_history_by_goods_id={"goods-1": [point]})

    assert asyncio.run(client.get_price_history("goods-1")) == [point]
    assert asyncio.run(client.get_price_history("goods-2")) == []



def test_dry_run_buff_client_does_not_execute_real_requests() -> None:
    client = DryRunBuffClient()

    assert asyncio.run(client.get_sell_orders("goods-1")) == []
    assert asyncio.run(client.get_buy_orders("goods-1")) == []
    assert asyncio.run(client.get_price_history("goods-1")) == []
    goods_info = asyncio.run(client.get_goods_info("goods-1"))
    assert goods_info.raw == {"dry_run": True}



def test_buff_http_client_public_methods_raise_not_implemented() -> None:
    client = BuffHttpClient(BuffClientConfig(base_url="https://example.test", dry_run=False))

    with pytest.raises(NotImplementedError, match="BUFF API endpoint mapping is not confirmed"):
        asyncio.run(client.get_sell_orders("goods-1"))
    with pytest.raises(NotImplementedError, match="BUFF API endpoint mapping is not confirmed"):
        asyncio.run(client.get_goods_info("goods-1"))
    with pytest.raises(NotImplementedError, match="BUFF API endpoint mapping is not confirmed"):
        asyncio.run(client.get_buy_orders("goods-1"))
    with pytest.raises(NotImplementedError, match="BUFF API endpoint mapping is not confirmed"):
        asyncio.run(client.get_price_history("goods-1"))



def test_buff_http_client_empty_base_url_has_explicit_behavior() -> None:
    client = BuffHttpClient(BuffClientConfig(base_url="", dry_run=False))

    with pytest.raises(ValueError, match="base_url"):
        asyncio.run(client._request_json("GET", "/placeholder"))



def test_buff_http_client_dry_run_disables_real_http_requests() -> None:
    client = BuffHttpClient(BuffClientConfig(base_url="https://example.test", dry_run=True))

    with pytest.raises(RuntimeError, match="dry_run mode is enabled"):
        asyncio.run(client._request_json("GET", "/placeholder"))



def test_buff_http_client_does_not_require_real_api_key() -> None:
    config = BuffClientConfig(base_url="https://example.test", api_key=None, api_secret=None)

    assert config.api_key is None
    assert config.api_secret is None
