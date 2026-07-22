import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
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
from app.clients.steamdt_errors import (
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
)
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.steamdt_rate_limiter import (
    SteamDTEndpoint,
    build_steamdt_rate_limit_policies,
)


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


class RecordingRateLimiter:
    def __init__(self, *, reject_on_acquire: bool = False) -> None:
        self.reject_on_acquire = reject_on_acquire
        self.acquired: list[SteamDTEndpoint] = []
        self.server_limits: list[tuple[SteamDTEndpoint, float | None]] = []

    async def acquire(self, endpoint: SteamDTEndpoint) -> None:
        self.acquired.append(endpoint)
        if self.reject_on_acquire:
            raise SteamDTRateLimitError(
                "local limit",
                endpoint=endpoint.value,
                retry_after_seconds=60,
            )

    async def record_server_limit(
        self,
        endpoint: SteamDTEndpoint,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.server_limits.append((endpoint, retry_after_seconds))


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



def test_steamdt_client_config_accepts_endpoint_specific_rate_limit_policies() -> None:
    policies = build_steamdt_rate_limit_policies(
        price_single_per_minute=30,
        price_batch_per_minute=1,
        price_avg_per_minute=5,
        base_per_day=1,
        kline_per_minute=60,
        wear_per_hour=100,
        price_batch_safety_buffer_seconds=7,
    )

    config = SteamDTClientConfig(rate_limit_policies=policies)

    assert config.rate_limit_policies[SteamDTEndpoint.PRICE_SINGLE].max_requests == 30
    assert config.rate_limit_policies[SteamDTEndpoint.PRICE_BATCH].safety_buffer_seconds == 7



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


class FailingCloseHttpClient:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_calls == 1:
            raise RuntimeError("close failed")


def test_steamdt_http_client_retries_close_after_underlying_failure() -> None:
    http_client = FailingCloseHttpClient()
    client = SteamDTHttpClient(
        SteamDTClientConfig(),
        http_client=http_client,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="close failed"):
        asyncio.run(client.aclose())
    asyncio.run(client.aclose())
    asyncio.run(client.aclose())

    assert http_client.close_calls == 2


def test_steamdt_http_client_get_price_single_candidates_preserves_complete_sequence() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "platform": "steam",
                "platformItemId": "first",
                "sellPrice": "12.3400",
                "sellCount": 0,
                "biddingPrice": "11.2500",
                "biddingCount": 2,
                "updateTime": 123456,
            },
            {
                "platform": "steam",
                "platformItemId": "duplicate",
                "sellPrice": "0",
                "sellCount": 7,
                "updateTime": "opaque",
            },
        ],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single_candidates("AK-47 | Redline"))

    assert [candidate.platform for candidate in result] == ["steam", "steam"]
    assert [candidate.platform_item_id for candidate in result] == [
        "first",
        "duplicate",
    ]
    assert result[0].sell_price_cny == Decimal("12.3400")
    assert result[0].sell_count == 0
    assert result[0].bidding_price_cny == Decimal("11.2500")
    assert result[0].bidding_count == 2
    assert result[0].update_time == 123456
    assert result[1].sell_price_cny == Decimal("0")
    assert result[1].update_time == "opaque"
    mock_http_client.request.assert_awaited_once()
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["url"] == "/open/cs2/v1/price/single"
    assert kwargs["params"] == {"marketHashName": "AK-47 | Redline"}


def test_steamdt_http_client_get_price_single_candidates_accepts_empty_and_unselectable() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        _response_with_request(200, {"success": True, "data": []}),
        _response_with_request(
            200,
            {
                "success": True,
                "data": [{"platform": "steam", "sellPrice": "0"}],
            },
        ),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    empty = asyncio.run(client.get_price_single_candidates("A"))
    unselectable = asyncio.run(client.get_price_single_candidates("A"))

    assert empty == []
    assert len(unselectable) == 1
    assert unselectable[0].sell_price_cny == Decimal("0")
    assert mock_http_client.request.await_count == 2


def test_candidates_acquire_single_bucket_before_each_transport_retry() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34"}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        httpx.ReadTimeout("timeout"),
        _response_with_request(200, payload),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    result = asyncio.run(client.get_price_single_candidates("A"))

    assert len(result) == 1
    assert limiter.acquired == [
        SteamDTEndpoint.PRICE_SINGLE,
        SteamDTEndpoint.PRICE_SINGLE,
    ]
    assert mock_http_client.request.await_count == 2


def test_candidates_5xx_retry_uses_single_endpoint_budget() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34"}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        _response_with_request(500, {"success": False}),
        _response_with_request(200, payload),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    result = asyncio.run(client.get_price_single_candidates("A"))

    assert len(result) == 1
    assert limiter.acquired == [
        SteamDTEndpoint.PRICE_SINGLE,
        SteamDTEndpoint.PRICE_SINGLE,
    ]
    assert mock_http_client.request.await_count == 2


def test_candidates_wrapper_4005_records_cooldown_without_retry() -> None:
    payload = {
        "success": False,
        "errorCode": 4005,
        "errorMsg": "limit",
        "errorCodeStr": "RATE_LIMIT",
        "data": None,
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single_candidates("A"))

    assert limiter.server_limits == [(SteamDTEndpoint.PRICE_SINGLE, None)]
    mock_http_client.request.assert_awaited_once()


def test_candidates_http_429_records_cooldown_without_retry() -> None:
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(429, {"success": False})
    response.headers["Retry-After"] = "2.5"
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single_candidates("A"))

    assert limiter.server_limits == [(SteamDTEndpoint.PRICE_SINGLE, 2.5)]
    mock_http_client.request.assert_awaited_once()


def test_candidates_local_limiter_rejection_skips_transport() -> None:
    limiter = RecordingRateLimiter(reject_on_acquire=True)
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single_candidates("A"))

    mock_http_client.request.assert_not_called()


def test_selected_single_price_preserves_original_payload_after_shared_fetch_refactor() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("A"))

    assert result.raw is not None
    assert result.raw["original_payload"] == payload
    mock_http_client.request.assert_awaited_once()



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

    with pytest.raises(SteamDTHttpStatusError, match="status_code=500"):
        asyncio.run(client.get_price_single("A"))



def test_steamdt_http_client_get_price_single_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, [])
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTResponseParseError, match="JSON object"):
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

    with pytest.raises(SteamDTHttpStatusError, match="status_code=500"):
        asyncio.run(client.get_price_batch(["A"]))



def test_steamdt_http_client_get_price_batch_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=[])
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTResponseParseError, match="JSON object"):
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

    with pytest.raises(SteamDTHttpStatusError, match="status_code=500"):
        asyncio.run(client.get_avg_price("AK-47 | Redline"))



def test_steamdt_http_client_get_avg_price_rejects_non_dict_json_payload() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=[])
    response.request = httpx.Request("GET", "https://open.steamdt.com/open/cs2/v1/price/avg")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTResponseParseError, match="JSON object"):
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




def test_steamdt_http_client_wrapper_error_4005_is_rate_limit_without_retry() -> None:
    payload = {
        "success": False,
        "errorCode": 4005,
        "errorMsg": "接口请求达到上限",
        "errorCodeStr": "RATE_LIMIT",
        "data": None,
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    assert exc_info.value.endpoint == "/open/cs2/v1/price/single"
    assert exc_info.value.error_code == 4005
    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_http_429_is_rate_limit_without_retry() -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(429, {"success": False})
    response.headers["Retry-After"] = "2.5"
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    assert exc_info.value.endpoint == "/open/cs2/v1/price/single"
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after_seconds == 2.5
    mock_http_client.request.assert_awaited_once()


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_steamdt_http_client_http_auth_and_not_found_errors_do_not_retry(
    status_code: int,
) -> None:
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(status_code, {"success": False})
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTHttpStatusError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    assert exc_info.value.status_code == status_code
    assert exc_info.value.endpoint == "/open/cs2/v1/price/single"
    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_parser_error_does_not_retry() -> None:
    payload = {"success": True, "data": {}}
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTResponseParseError):
        asyncio.run(client.get_price_single("A"))

    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_timeout_retries_until_success() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    response = _response_with_request(200, payload)
    mock_http_client.request.side_effect = [httpx.ReadTimeout("timeout"), response]
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("A"))

    assert result.price_cny == Decimal("12.34")
    assert mock_http_client.request.await_count == 2


def test_steamdt_http_client_http_500_retries_until_success() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    first = _response_with_request(500, {"success": False})
    second = _response_with_request(200, payload)
    mock_http_client.request.side_effect = [first, second]
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    result = asyncio.run(client.get_price_single("A"))

    assert result.price_cny == Decimal("12.34")
    assert mock_http_client.request.await_count == 2


def test_steamdt_http_client_typed_error_does_not_leak_api_key() -> None:
    config = SteamDTClientConfig(
        api_key="super-secret-steamdt-key",
        dry_run=False,
        max_retries=0,
    )
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = httpx.ConnectError(
        "Authorization: Bearer super-secret-steamdt-key"
    )
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTTransportError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    error_text = str(exc_info.value)
    assert exc_info.value.endpoint == "/open/cs2/v1/price/single"
    assert "super-secret-steamdt-key" not in error_text
    assert "Authorization:" not in error_text


def test_steamdt_http_client_single_uses_price_single_bucket() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_price_single("A"))

    assert limiter.acquired == [SteamDTEndpoint.PRICE_SINGLE]


def test_steamdt_http_client_batch_uses_price_batch_bucket() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "12.34"}],
            }
        ],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_price_batch(["A"]))

    assert limiter.acquired == [SteamDTEndpoint.PRICE_BATCH]


def test_steamdt_http_client_avg_uses_price_avg_bucket() -> None:
    payload = {
        "success": True,
        "data": {"marketHashName": "A", "avgPrice": "12.34", "dataList": []},
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = httpx.Response(200, json=payload)
    response.request = httpx.Request("GET", "https://open.steamdt.com/open/cs2/v1/price/avg")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_avg_price("A"))

    assert limiter.acquired == [SteamDTEndpoint.PRICE_AVG]


def test_steamdt_http_client_acquires_before_each_http_attempt() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        httpx.ReadTimeout("timeout"),
        _response_with_request(200, payload),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_price_single("A"))

    assert limiter.acquired == [
        SteamDTEndpoint.PRICE_SINGLE,
        SteamDTEndpoint.PRICE_SINGLE,
    ]
    assert mock_http_client.request.await_count == 2


def test_steamdt_http_client_local_limiter_rejection_does_not_call_transport() -> None:
    limiter = RecordingRateLimiter(reject_on_acquire=True)
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(client.get_price_single("A"))

    assert exc_info.value.endpoint == SteamDTEndpoint.PRICE_SINGLE.value
    mock_http_client.request.assert_not_called()


def test_steamdt_http_client_wrapper_4005_records_server_limit() -> None:
    payload = {
        "success": False,
        "errorCode": 4005,
        "errorMsg": "接口请求达到上限",
        "errorCodeStr": "RATE_LIMIT",
        "data": None,
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single("A"))

    assert limiter.server_limits == [(SteamDTEndpoint.PRICE_SINGLE, None)]
    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_http_429_records_server_limit() -> None:
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    response = _response_with_request(429, {"success": False})
    response.headers["Retry-After"] = "2.5"
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single("A"))

    assert limiter.server_limits == [(SteamDTEndpoint.PRICE_SINGLE, 2.5)]
    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_parser_error_does_not_record_server_limit() -> None:
    limiter = RecordingRateLimiter()
    payload = {"success": True, "data": {}}
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(200, payload)
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTResponseParseError):
        asyncio.run(client.get_price_single("A"))

    assert limiter.server_limits == []


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_steamdt_http_client_401_403_404_do_not_record_server_limit(
    status_code: int,
) -> None:
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=3)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _response_with_request(status_code, {"success": False})
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTHttpStatusError):
        asyncio.run(client.get_price_single("A"))

    assert limiter.server_limits == []
    mock_http_client.request.assert_awaited_once()


def test_steamdt_http_client_5xx_retry_uses_endpoint_budget() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        _response_with_request(500, {"success": False}),
        _response_with_request(200, payload),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_price_single("A"))

    assert limiter.acquired == [
        SteamDTEndpoint.PRICE_SINGLE,
        SteamDTEndpoint.PRICE_SINGLE,
    ]
    assert mock_http_client.request.await_count == 2


def test_steamdt_http_client_transport_retry_uses_endpoint_budget() -> None:
    payload = {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }
    limiter = RecordingRateLimiter()
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        httpx.ConnectError("connection failed"),
        _response_with_request(200, payload),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(client.get_price_single("A"))

    assert limiter.acquired == [
        SteamDTEndpoint.PRICE_SINGLE,
        SteamDTEndpoint.PRICE_SINGLE,
    ]
    assert mock_http_client.request.await_count == 2


def test_steamdt_http_client_batch_5xx_retry_cannot_bypass_one_per_minute_budget() -> None:
    policies = build_steamdt_rate_limit_policies(price_batch_per_minute=1)
    config = SteamDTClientConfig(
        api_key="secret-key",
        dry_run=False,
        max_retries=1,
        rate_limit_policies=policies,
    )
    mock_http_client = AsyncMock()
    response = httpx.Response(500, json={"success": False})
    response.request = httpx.Request("POST", "https://open.steamdt.com/open/cs2/v1/price/batch")
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(client.get_price_batch(["A"]))

    assert exc_info.value.endpoint == SteamDTEndpoint.PRICE_BATCH.value
    assert mock_http_client.request.await_count == 1


def test_steamdt_http_client_dry_run_does_not_acquire_or_request() -> None:
    limiter = RecordingRateLimiter()
    mock_http_client = AsyncMock()
    client = SteamDTHttpClient(
        SteamDTClientConfig(api_key=None, dry_run=True),
        http_client=mock_http_client,
        rate_limiter=limiter,
    )

    with pytest.raises(RuntimeError, match="dry-run mode"):
        asyncio.run(client.get_price_single("A"))

    assert limiter.acquired == []
    mock_http_client.request.assert_not_called()


def _clear_steamdt_smoke_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "STEAMDT_API_KEY",
        "STEAMDT_DRY_RUN",
        "STEAMDT_SMOKE_MARKET_HASH_NAME",
        "STEAMDT_SMOKE_MARKET_HASH_NAMES",
        "STEAMDT_ENABLE_AVG_SANITY_CHECK",
        "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
        "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE",
        "STEAMDT_PROVIDER_BATCH_MODE",
        "STEAMDT_PROVIDER_MAX_AVG_REQUESTS_PER_BATCH",
    ]:
        monkeypatch.delenv(name, raising=False)



def test_steamdt_single_smoke_default_dry_run_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_single_smoke

    _clear_steamdt_smoke_env(monkeypatch)

    asyncio.run(steamdt_price_single_smoke._run())

    assert "STEAMDT_DRY_RUN is not false" in capsys.readouterr().out



def test_steamdt_batch_smoke_default_dry_run_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_batch_smoke

    _clear_steamdt_smoke_env(monkeypatch)

    asyncio.run(steamdt_price_batch_smoke._run())

    assert "STEAMDT_DRY_RUN is not false" in capsys.readouterr().out



def test_steamdt_avg_smoke_default_dry_run_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_avg_price_smoke

    _clear_steamdt_smoke_env(monkeypatch)

    asyncio.run(steamdt_avg_price_smoke._run())

    assert "STEAMDT_DRY_RUN is not false" in capsys.readouterr().out



@pytest.mark.parametrize(
    ("module_name", "expected_message"),
    [
        ("steamdt_price_single_smoke", "STEAMDT_API_KEY is missing"),
        ("steamdt_price_batch_smoke", "STEAMDT_API_KEY is missing"),
        ("steamdt_avg_price_smoke", "STEAMDT_API_KEY is missing"),
    ],
)
def test_steamdt_smoke_scripts_missing_api_key_do_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    expected_message: str,
) -> None:
    import importlib

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    module = importlib.import_module(f"scripts.{module_name}")

    asyncio.run(module._run())

    assert expected_message in capsys.readouterr().out



def test_steamdt_single_smoke_missing_market_hash_name_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_single_smoke

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    monkeypatch.setenv("STEAMDT_API_KEY", "secret-key")

    asyncio.run(steamdt_price_single_smoke._run())

    assert "STEAMDT_SMOKE_MARKET_HASH_NAME is missing" in capsys.readouterr().out



def test_steamdt_avg_smoke_missing_market_hash_name_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_avg_price_smoke

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    monkeypatch.setenv("STEAMDT_API_KEY", "secret-key")

    asyncio.run(steamdt_avg_price_smoke._run())

    assert "STEAMDT_SMOKE_MARKET_HASH_NAME is missing" in capsys.readouterr().out



def test_steamdt_batch_smoke_missing_market_hash_names_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_batch_smoke

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    monkeypatch.setenv("STEAMDT_API_KEY", "secret-key")

    asyncio.run(steamdt_price_batch_smoke._run())

    assert "STEAMDT_SMOKE_MARKET_HASH_NAMES is missing" in capsys.readouterr().out



def test_steamdt_batch_smoke_rejects_more_than_ten_names(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_batch_smoke

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    monkeypatch.setenv("STEAMDT_API_KEY", "secret-key")
    monkeypatch.setenv(
        "STEAMDT_SMOKE_MARKET_HASH_NAMES",
        ",".join(f"Item {index}" for index in range(11)),
    )

    asyncio.run(steamdt_price_batch_smoke._run())

    assert "maximum 10 market hash names" in capsys.readouterr().out



def test_steamdt_single_smoke_invalid_decimal_env_does_not_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import steamdt_price_single_smoke

    _clear_steamdt_smoke_env(monkeypatch)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    monkeypatch.setenv("STEAMDT_API_KEY", "secret-key")
    monkeypatch.setenv("STEAMDT_SMOKE_MARKET_HASH_NAME", "A")
    monkeypatch.setenv("STEAMDT_ENABLE_AVG_SANITY_CHECK", "true")
    monkeypatch.setenv("STEAMDT_MAX_PRICE_TO_AVG_RATIO", "not-a-decimal")

    asyncio.run(steamdt_price_single_smoke._run())

    assert "must be a valid decimal value" in capsys.readouterr().out



def test_steamdt_smoke_utils_parse_and_redact_helpers() -> None:
    from scripts.steamdt_smoke_utils import (
        is_explicit_false,
        parse_bool_env,
        parse_decimal_env,
        parse_market_hash_names,
        redact_message,
        summarize_quote_raw,
    )

    environ = {
        "BOOL_TRUE": "true",
        "BOOL_FALSE": "false",
        "RATIO": "1.50",
    }

    assert parse_bool_env(environ, "BOOL_TRUE") is True
    assert parse_bool_env(environ, "BOOL_FALSE") is False
    assert is_explicit_false(environ, "BOOL_FALSE") is True
    assert parse_decimal_env(environ, "RATIO", "1.0") == Decimal("1.50")
    assert parse_market_hash_names(" A, B, A ,, ") == ["A", "B"]
    assert "super-secret" not in redact_message(
        "Authorization: Bearer super-secret-token",
        api_key="super-secret-token",
    )
    assert summarize_quote_raw(
        {
            "selected_strategy": "liquidity_aware_sell_price",
            "reason_codes": ["LIQUIDITY_ACCEPTED"],
            "selected_platform": "steam",
            "platform_prices": [{"full": "raw"}],
            "original_payload": {"should": "not be printed"},
        }
    ) == {
        "selected_strategy": "liquidity_aware_sell_price",
        "reason_codes": ["LIQUIDITY_ACCEPTED"],
        "selected_platform": "steam",
        "candidate_count": 1,
    }



@pytest.mark.parametrize(
    "script_name",
    [
        "steamdt_price_single_smoke",
        "steamdt_price_batch_smoke",
        "steamdt_avg_price_smoke",
        "steamdt_provider_price_smoke",
    ],
)
@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_steamdt_smoke_script_entrypoints_support_dry_run_without_import_error(
    script_name: str,
    entrypoint: str,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["STEAMDT_DRY_RUN"] = "true"
    env.pop("STEAMDT_API_KEY", None)

    if entrypoint == "direct":
        command = [sys.executable, f"scripts/{script_name}.py"]
    else:
        command = [sys.executable, "-m", f"scripts.{script_name}"]

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0
    assert "ModuleNotFoundError" not in combined_output
    assert "Authorization:" not in combined_output
    assert "STEAMDT_DRY_RUN is not false" in combined_output
