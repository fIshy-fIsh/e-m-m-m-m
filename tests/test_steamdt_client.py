import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.steamdt_client import (
    DryRunSteamDTClient,
    MockSteamDTClient,
    SteamDTBaseItemInfo,
    SteamDTBatchPriceResult,
    SteamDTClientConfig,
    SteamDTHistoricalPricePoint,
    SteamDTHttpClient,
    SteamDTPriceQuote,
    SteamDTWearInfo,
)
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig


def _make_price_quote(name: str = "AK-47 | Redline") -> SteamDTPriceQuote:
    return SteamDTPriceQuote(
        market_hash_name=name,
        price_cny=Decimal("123.45"),
        raw={"source": "test"},
    )



def _make_base_item_info(name: str = "AK-47 | Redline") -> SteamDTBaseItemInfo:
    return SteamDTBaseItemInfo(
        market_hash_name=name,
        raw={"source": "test"},
    )



def _make_historical_price_point(
    name: str = "AK-47 | Redline",
) -> SteamDTHistoricalPricePoint:
    return SteamDTHistoricalPricePoint(
        market_hash_name=name,
        timestamp=datetime.now(UTC),
        price_cny=Decimal("100.00"),
        raw={"source": "test"},
    )



def _make_wear_info() -> SteamDTWearInfo:
    return SteamDTWearInfo(
        inspect_link="steam://inspect/test",
        float_value=0.12,
        paint_seed=123,
        raw={"source": "test"},
    )



def _response_with_request(status_code: int, payload) -> httpx.Response:
    response = httpx.Response(status_code, json=payload)
    response.request = httpx.Request(
        "GET",
        "https://open.steamdt.com/open/cs2/v1/price/single",
    )
    return response



def test_steamdt_client_config_creates_successfully() -> None:
    config = SteamDTClientConfig()
    assert config.base_url == "https://open.steamdt.com"



def test_steamdt_client_config_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        SteamDTClientConfig(base_url="")



def test_steamdt_client_config_requires_api_key_when_not_dry_run() -> None:
    with pytest.raises(ValueError, match="api_key"):
        SteamDTClientConfig(dry_run=False, api_key=None)



def test_steamdt_client_config_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        SteamDTClientConfig(timeout_seconds=0)



def test_steamdt_client_config_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        SteamDTClientConfig(max_retries=-1)



def test_steamdt_client_config_rejects_non_positive_rate_limit() -> None:
    with pytest.raises(ValueError, match="rate_limit_per_minute"):
        SteamDTClientConfig(rate_limit_per_minute=0)



def test_steamdt_client_config_repr_does_not_leak_api_key() -> None:
    config = SteamDTClientConfig(api_key="secret-key")
    assert "secret-key" not in repr(config)
    assert "[REDACTED]" in repr(config)



def test_steamdt_price_quote_creates_successfully() -> None:
    quote = _make_price_quote()
    assert quote.market_hash_name == "AK-47 | Redline"



def test_steamdt_price_quote_raises_when_market_hash_name_empty() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        SteamDTPriceQuote(market_hash_name="", price_cny=Decimal("1"))



def test_steamdt_price_quote_raises_when_price_negative() -> None:
    with pytest.raises(ValueError, match="price_cny"):
        SteamDTPriceQuote(market_hash_name="AK-47 | Redline", price_cny=Decimal("-1"))



def test_steamdt_batch_price_result_creates_successfully() -> None:
    result = SteamDTBatchPriceResult(quotes={}, missing=[])
    assert result.quotes == {}



def test_steamdt_base_item_info_raises_when_market_hash_name_empty() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        SteamDTBaseItemInfo(market_hash_name="", raw={})



def test_steamdt_historical_price_point_creates_successfully() -> None:
    point = _make_historical_price_point()
    assert point.timestamp.tzinfo is not None



def test_steamdt_historical_price_point_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        SteamDTHistoricalPricePoint(
            market_hash_name="AK-47 | Redline",
            timestamp=datetime.now(),
            price_cny=Decimal("1"),
        )



def test_steamdt_historical_price_point_rejects_negative_price() -> None:
    with pytest.raises(ValueError, match="price_cny"):
        SteamDTHistoricalPricePoint(
            market_hash_name="AK-47 | Redline",
            timestamp=datetime.now(UTC),
            price_cny=Decimal("-1"),
        )



def test_steamdt_wear_info_rejects_float_below_zero() -> None:
    with pytest.raises(ValueError, match="float_value"):
        SteamDTWearInfo(inspect_link=None, float_value=-0.1, paint_seed=None)



def test_steamdt_wear_info_rejects_float_above_one() -> None:
    with pytest.raises(ValueError, match="float_value"):
        SteamDTWearInfo(inspect_link=None, float_value=1.1, paint_seed=None)



def test_steamdt_wear_info_rejects_negative_paint_seed() -> None:
    with pytest.raises(ValueError, match="paint_seed"):
        SteamDTWearInfo(inspect_link=None, float_value=0.1, paint_seed=-1)



def test_mock_steamdt_client_get_price_single_returns_quote() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"AK-47 | Redline": _make_price_quote()})
    result = asyncio.run(client.get_price_single("AK-47 | Redline"))
    assert result.market_hash_name == "AK-47 | Redline"



def test_mock_steamdt_client_get_price_single_raises_when_missing() -> None:
    client = MockSteamDTClient()
    with pytest.raises(RuntimeError, match="missing mock SteamDT single price"):
        asyncio.run(client.get_price_single("AK-47 | Redline"))



def test_mock_steamdt_client_get_price_batch_returns_quotes_and_missing() -> None:
    client = MockSteamDTClient(price_quotes_by_name={"A": _make_price_quote("A")})
    result = asyncio.run(client.get_price_batch(["A", "B"]))
    assert "A" in result.quotes
    assert result.missing == ["B"]



def test_mock_steamdt_client_get_base_item_info_returns_data() -> None:
    client = MockSteamDTClient(base_info_by_name={"A": _make_base_item_info("A")})
    result = asyncio.run(client.get_base_item_info("A"))
    assert result.market_hash_name == "A"



def test_mock_steamdt_client_get_kline_returns_data_or_empty() -> None:
    point = _make_historical_price_point("A")
    client = MockSteamDTClient(kline_by_name={"A": [point]})
    assert asyncio.run(client.get_kline("A")) == [point]
    assert asyncio.run(client.get_kline("B")) == []



def test_mock_steamdt_client_get_wear_info_returns_data() -> None:
    wear = _make_wear_info()
    client = MockSteamDTClient(wear_info_by_inspect_link={"steam://inspect/test": wear})
    result = asyncio.run(client.get_wear_info("steam://inspect/test"))
    assert result == wear



def test_dry_run_steamdt_client_get_price_single_raises() -> None:
    client = DryRunSteamDTClient()
    with pytest.raises(RuntimeError, match="dry-run mode enabled"):
        asyncio.run(client.get_price_single("AK-47 | Redline"))



def test_dry_run_steamdt_client_get_price_batch_returns_empty_quotes_and_missing() -> None:
    client = DryRunSteamDTClient()
    result = asyncio.run(client.get_price_batch(["A", "B"]))
    assert result.quotes == {}
    assert result.missing == ["A", "B"]



def test_dry_run_steamdt_client_get_kline_returns_empty_list() -> None:
    client = DryRunSteamDTClient()
    assert asyncio.run(client.get_kline("AK-47 | Redline")) == []



def test_dry_run_steamdt_client_get_wear_info_raises() -> None:
    client = DryRunSteamDTClient()
    with pytest.raises(RuntimeError, match="dry-run mode enabled"):
        asyncio.run(client.get_wear_info("steam://inspect/test"))



def test_steamdt_http_client_request_json_rejects_real_http_in_dry_run() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig(dry_run=True))
    with pytest.raises(RuntimeError, match="dry-run mode"):
        asyncio.run(client._request_json("GET", "/path"))



def test_steamdt_http_client_public_methods_keep_other_endpoints_not_implemented() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig())
    with pytest.raises(RuntimeError, match="dry-run mode"):
        asyncio.run(client.get_price_single("AK-47 | Redline"))
    result = asyncio.run(client.get_price_batch(["A"]))
    assert result.quotes == {}
    assert result.missing == ["A"]
    with pytest.raises(NotImplementedError, match="docs/STEAMDT_API_NOTES.md"):
        asyncio.run(client.get_base_item_info("AK-47 | Redline"))
    with pytest.raises(NotImplementedError, match="docs/STEAMDT_API_NOTES.md"):
        asyncio.run(client.get_kline("AK-47 | Redline"))
    with pytest.raises(NotImplementedError, match="docs/STEAMDT_API_NOTES.md"):
        asyncio.run(client.get_wear_info("steam://inspect/test"))



def test_steamdt_http_client_does_not_require_real_api_key_in_dry_run() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig(api_key=None, dry_run=True))
    assert client.config.api_key is None



def test_steamdt_http_client_get_price_single_uses_official_single_path_and_query_param() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "platform": "steam",
                "sellPrice": "12.34",
                "sellCount": 2,
                "biddingPrice": "11.11",
                "biddingCount": 1,
                "updateTime": 123456,
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("AK-47 | Redline"))

    assert result.market_hash_name == "AK-47 | Redline"
    assert result.price_cny == Decimal("12.34")
    mock_http_client.request.assert_awaited_once()
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/single"
    assert kwargs["params"] == {"marketHashName": "AK-47 | Redline"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"



def test_steamdt_http_client_get_price_single_selects_lowest_positive_sell_price() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "12.34"},
            {"platform": "buff", "sellPrice": "11.00"},
            {"platform": "other", "sellPrice": "0"},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("A"))

    assert result.price_cny == Decimal("11.00")
    assert result.raw["selected_strategy"] == "lowest_positive_sell_price"



def test_steamdt_http_client_get_price_single_rejects_when_no_positive_sell_price_exists() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": None},
            {"platform": "buff", "sellPrice": "0"},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="acceptable sellPrice"):
        asyncio.run(client.get_price_single("A"))



def test_steamdt_http_client_get_price_single_propagates_wrapper_failure() -> None:
    payload = {
        "success": False,
        "errorCode": 1,
        "errorMsg": "boom",
        "errorCodeStr": "ERR",
        "data": None,
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(client.get_price_single("A"))



def test_steamdt_http_client_get_price_single_rejects_non_2xx_response() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(500, {"success": False})
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_price_single("A"))



def test_steamdt_http_client_get_price_single_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, [])
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_price_single("A"))



def test_steamdt_http_client_get_price_single_error_does_not_leak_api_key() -> None:
    config = SteamDTClientConfig(
        api_key="super-secret-steamdt-key",
        dry_run=False,
        max_retries=0,
    )
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = httpx.ConnectError("boom")
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    assert "super-secret-steamdt-key" not in str(exc_info.value)



def test_steamdt_http_client_get_price_batch_empty_list_returns_empty_result() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig())

    result = asyncio.run(client.get_price_batch([]))

    assert result.quotes == {}
    assert result.missing == []
    assert result.raw is None



def test_steamdt_http_client_get_price_batch_strips_empty_names_and_deduplicates_in_order() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "10.00"}],
            },
            {
                "marketHashName": "B",
                "dataList": [{"platform": "steam", "sellPrice": "20.00"}],
            },
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request(
        "POST",
        "https://open.steamdt.com/open/cs2/v1/price/batch",
        json={"marketHashNames": ["A", "B"]},
    )
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A", "", "B", "A", "  "]))

    assert list(result.quotes.keys()) == ["A", "B"]
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/batch"
    assert kwargs["json"] == {"marketHashNames": ["A", "B"]}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"



def test_steamdt_http_client_get_price_batch_dry_run_returns_missing_without_request() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig(dry_run=True))

    result = asyncio.run(client.get_price_batch(["A", "B"]))

    assert result.quotes == {}
    assert result.missing == ["A", "B"]



def test_steamdt_http_client_get_price_batch_selects_lowest_positive_sell_price_per_name() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [
                    {"platform": "steam", "sellPrice": "12.00"},
                    {"platform": "buff", "sellPrice": "10.00"},
                ],
            },
            {
                "marketHashName": "B",
                "dataList": [
                    {"platform": "steam", "sellPrice": "8.00"},
                    {"platform": "buff", "sellPrice": "9.00"},
                ],
            },
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A", "B"]))

    assert result.quotes["A"].price_cny == Decimal("10.00")
    assert result.quotes["B"].price_cny == Decimal("8.00")



def test_steamdt_http_client_get_price_batch_marks_name_missing_when_no_positive_sell_price(
) -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "0"}],
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A"]))

    assert result.quotes == {}
    assert result.missing == ["A"]



def test_steamdt_http_client_get_price_batch_marks_requested_name_missing_if_response_omits_it(
) -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "10.00"}],
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A", "B"]))

    assert "A" in result.quotes
    assert result.missing == ["B"]



def test_steamdt_http_client_get_price_batch_ignores_unrequested_extra_name() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "10.00"}],
            },
            {
                "marketHashName": "EXTRA",
                "dataList": [{"platform": "steam", "sellPrice": "99.00"}],
            },
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A"]))

    assert list(result.quotes.keys()) == ["A"]
    assert "EXTRA" not in result.quotes



def test_steamdt_http_client_get_price_batch_propagates_wrapper_failure() -> None:
    payload = {
        "success": False,
        "errorCode": 1,
        "errorMsg": "boom",
        "errorCodeStr": "ERR",
        "data": None,
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(client.get_price_batch(["A"]))



def test_steamdt_http_client_get_price_batch_rejects_non_2xx_response() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(500)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_price_batch(["A"]))



def test_steamdt_http_client_get_price_batch_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=[])
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_price_batch(["A"]))



def test_steamdt_http_client_get_avg_price_rejects_real_http_in_dry_run() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig(dry_run=True))

    with pytest.raises(RuntimeError, match="dry-run mode"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_avg_price_uses_official_path_and_query_param() -> None:
    payload = {
        "success": True,
        "data": {
            "marketHashName": "AK-47 | Redline",
            "avgPrice": "123.45",
            "dataList": [{"platform": "steam", "avgPrice": "122.00"}],
        },
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request(
        "GET",
        "https://open.steamdt.com/open/cs2/v1/price/avg",
    )
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_avg_price("AK-47 | Redline"))

    assert result.market_hash_name == "AK-47 | Redline"
    assert result.avg_price_cny == Decimal("123.45")
    assert result.platform_avg_prices["steam"] == Decimal("122.00")
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/avg"
    assert kwargs["params"] == {"marketHashName": "AK-47 | Redline"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"



def test_steamdt_http_client_get_avg_price_rejects_market_hash_name_mismatch() -> None:
    payload = {
        "success": True,
        "data": {
            "marketHashName": "Other Name",
            "avgPrice": "123.45",
            "dataList": [{"platform": "steam", "avgPrice": "122.00"}],
        },
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request(
        "GET",
        "https://open.steamdt.com/open/cs2/v1/price/avg",
    )
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_avg_price_propagates_wrapper_failure() -> None:
    payload = {
        "success": False,
        "errorCode": 1,
        "errorMsg": "boom",
        "errorCodeStr": "ERR",
        "data": None,
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request(
        "GET",
        "https://open.steamdt.com/open/cs2/v1/price/avg",
    )
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_avg_price_rejects_non_2xx_response() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(500)
    response.request = httpx.Request("GET", "https://open.steamdt.com/open/cs2/v1/price/avg")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_avg_price_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=[])
    response.request = httpx.Request("GET", "https://open.steamdt.com/open/cs2/v1/price/avg")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="SteamDT HTTP request failed"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_price_single_default_does_not_call_avg_endpoint() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "platform": "steam",
                "sellPrice": "12.34",
                "sellCount": 2,
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("AK-47 | Redline"))

    assert result.price_cny == Decimal("12.34")
    mock_http_client.request.assert_awaited_once()
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/single"



def test_steamdt_http_client_get_price_batch_default_does_not_call_avg_endpoint() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [
                    {"platform": "steam", "sellPrice": "10.00", "sellCount": 2}
                ],
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_batch(["A"]))

    assert result.quotes["A"].price_cny == Decimal("10.00")
    mock_http_client.request.assert_awaited_once()
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/batch"



def test_steamdt_http_client_get_price_single_with_selection_uses_avg_sanity() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "14.00", "sellCount": 2},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(
        client.get_price_single_with_selection(
            "A",
            selection_config=SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=Decimal("1.5"),
                fallback_to_lowest_positive=False,
            ),
            avg_price_cny=Decimal("10.00"),
        )
    )

    assert result.price_cny == Decimal("14.00")
    assert result.raw["selected_strategy"] == "liquidity_aware_sell_price"



def test_steamdt_http_client_get_price_single_avg_sanity_rejects_high_sell_price() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "20.00", "sellCount": 2},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError, match="NO_ACCEPTED_LIQUID_PRICE"):
        asyncio.run(
            client.get_price_single_with_selection(
                "A",
                selection_config=SteamDTPriceSelectionConfig(
                    max_price_to_avg_ratio=Decimal("1.5"),
                    fallback_to_lowest_positive=False,
                ),
                avg_price_cny=Decimal("10.00"),
            )
        )



def test_steamdt_http_client_get_price_single_avg_sanity_error_does_not_leak_api_key() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "20.00", "sellCount": 2},
        ],
    }
    config = SteamDTClientConfig(
        api_key="super-secret-steamdt-key",
        dry_run=False,
        max_retries=0,
    )
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            client.get_price_single_with_selection(
                "A",
                selection_config=SteamDTPriceSelectionConfig(
                    max_price_to_avg_ratio=Decimal("1.5"),
                    fallback_to_lowest_positive=False,
                ),
                avg_price_cny=Decimal("10.00"),
            )
        )

    assert "super-secret-steamdt-key" not in str(exc_info.value)



def test_steamdt_http_client_get_price_batch_with_selection_uses_avg_sanity() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [
                    {"platform": "steam", "sellPrice": "14.00", "sellCount": 2}
                ],
            }
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(
        client.get_price_batch_with_selection(
            ["A"],
            selection_config=SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=Decimal("1.5"),
                fallback_to_lowest_positive=False,
            ),
            avg_prices_by_name={"A": Decimal("10.00")},
        )
    )

    assert result.quotes["A"].price_cny == Decimal("14.00")
    assert result.missing == []



def test_steamdt_http_client_get_price_batch_avg_sanity_rejects_name_into_missing() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [
                    {"platform": "steam", "sellPrice": "20.00", "sellCount": 2}
                ],
            },
            {
                "marketHashName": "B",
                "dataList": [
                    {"platform": "steam", "sellPrice": "10.00", "sellCount": 2}
                ],
            },
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(
        client.get_price_batch_with_selection(
            ["A", "B"],
            selection_config=SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=Decimal("1.5"),
                fallback_to_lowest_positive=False,
            ),
            avg_prices_by_name={"A": Decimal("10.00"), "B": Decimal("10.00")},
        )
    )

    assert "A" not in result.quotes
    assert result.quotes["B"].price_cny == Decimal("10.00")
    assert result.missing == ["A"]



def test_steamdt_http_client_get_price_single_skips_avg_sanity_when_avg_price_is_none() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "20.00", "sellCount": 2},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(
        client.get_price_single_with_selection(
            "A",
            selection_config=SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=Decimal("1.5"),
                fallback_to_lowest_positive=False,
            ),
            avg_price_cny=None,
        )
    )

    assert result.price_cny == Decimal("20.00")



def test_steamdt_http_client_get_price_single_skips_avg_sanity_when_ratio_is_none() -> None:
    payload = {
        "success": True,
        "data": [
            {"platform": "steam", "sellPrice": "20.00", "sellCount": 2},
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(
        client.get_price_single_with_selection(
            "A",
            selection_config=SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=None,
                fallback_to_lowest_positive=False,
            ),
            avg_price_cny=Decimal("10.00"),
        )
    )

    assert result.price_cny == Decimal("20.00")
