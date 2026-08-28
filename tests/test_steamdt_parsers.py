from decimal import Decimal

import pytest

from app.clients.steamdt_client import (
    SteamDTAvgPrice,
    SteamDTPlatformPrice,
    SteamDTWearParseResult,
    _require_response_wrapper,
    _to_decimal_or_none,
    _to_int_or_none,
    parse_avg_price_response,
    parse_base_item_info_response,
    parse_kline_response,
    parse_price_batch_response,
    parse_price_single_response,
    parse_wear_response,
)


def test_require_response_wrapper_returns_data_on_success() -> None:
    assert _require_response_wrapper({"success": True, "data": {"ok": True}}) == {"ok": True}



def test_require_response_wrapper_raises_on_failed_success() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        _require_response_wrapper(
            {
                "success": False,
                "errorCode": 1,
                "errorMsg": "boom",
                "errorCodeStr": "ERR",
                "data": None,
            }
        )



def test_require_response_wrapper_raises_when_data_missing() -> None:
    with pytest.raises(RuntimeError, match="missing data"):
        _require_response_wrapper({"success": True})



def test_to_decimal_or_none_supports_basic_types() -> None:
    assert _to_decimal_or_none("1.23") == Decimal("1.23")
    assert _to_decimal_or_none(1) == Decimal("1")
    assert _to_decimal_or_none(1.5) == Decimal("1.5")
    assert _to_decimal_or_none(None) is None



def test_to_decimal_or_none_raises_on_invalid_value() -> None:
    with pytest.raises(ValueError):
        _to_decimal_or_none(object())



def test_to_int_or_none_supports_basic_types() -> None:
    assert _to_int_or_none("3") == 3
    assert _to_int_or_none(4) == 4
    assert _to_int_or_none(None) is None



def test_to_int_or_none_raises_on_invalid_value() -> None:
    with pytest.raises(ValueError):
        _to_int_or_none("not-an-int")



def test_to_int_or_none_rejects_non_integer_float() -> None:
    with pytest.raises(ValueError):
        _to_int_or_none(1.5)



def test_parse_price_single_response_parses_platform_records() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "platform": "steam",
                "platformItemId": "123",
                "sellPrice": "10.5",
                "sellCount": "2",
                "biddingPrice": "9.5",
                "biddingCount": 1,
                "updateTime": 123456,
            }
        ],
    }

    result = parse_price_single_response("AK-47 | Redline", payload)

    assert len(result) == 1
    assert isinstance(result[0], SteamDTPlatformPrice)
    assert result[0].sell_price_cny == Decimal("10.5")
    assert result[0].bidding_price_cny == Decimal("9.5")
    assert result[0].sell_count == 2
    assert result[0].bidding_count == 1



def test_parse_price_single_response_rejects_non_list_data() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        parse_price_single_response("A", {"success": True, "data": {}})



def test_parse_price_single_response_requires_platform() -> None:
    with pytest.raises(ValueError, match="platform"):
        parse_price_single_response("A", {"success": True, "data": [{}]})



def test_parse_price_single_response_preserves_raw() -> None:
    item = {
        "platform": "steam",
        "platformItemId": "123",
        "sellPrice": "10.5",
        "sellCount": "2",
        "biddingPrice": "9.5",
        "biddingCount": 1,
        "updateTime": 123456,
    }
    result = parse_price_single_response("A", {"success": True, "data": [item]})

    assert result[0].raw == item



def test_parse_price_single_response_requires_market_hash_name() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        parse_price_single_response("", {"success": True, "data": []})



def test_parse_price_batch_response_parses_grouped_platform_prices() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "marketHashName": "A",
                "dataList": [{"platform": "steam", "sellPrice": "11.0"}],
            }
        ],
    }

    result = parse_price_batch_response(["A"], payload)

    assert "A" in result
    assert result["A"][0].sell_price_cny == Decimal("11.0")



def test_parse_price_batch_response_missing_datalist_returns_empty_list() -> None:
    payload = {"success": True, "data": [{"marketHashName": "A"}]}
    result = parse_price_batch_response(["A"], payload)
    assert result["A"] == []



def test_parse_price_batch_response_none_datalist_returns_empty_list() -> None:
    payload = {"success": True, "data": [{"marketHashName": "A", "dataList": None}]}
    result = parse_price_batch_response(["A"], payload)
    assert result["A"] == []



def test_parse_price_batch_response_rejects_non_list_datalist() -> None:
    with pytest.raises(ValueError, match="dataList"):
        parse_price_batch_response(
            ["A"],
            {"success": True, "data": [{"marketHashName": "A", "dataList": {}}]},
        )



def test_parse_price_batch_response_requires_market_hash_name() -> None:
    with pytest.raises(ValueError, match="marketHashName"):
        parse_price_batch_response([], {"success": True, "data": [{"dataList": []}]})



def test_parse_avg_price_response_parses_avg_price() -> None:
    payload = {
        "success": True,
        "data": {
            "marketHashName": "A",
            "avgPrice": "20.5",
            "dataList": [{"platform": "steam", "avgPrice": "19.5"}],
        },
    }

    result = parse_avg_price_response("A", payload)

    assert isinstance(result, SteamDTAvgPrice)
    assert result.avg_price_cny == Decimal("20.5")
    assert result.platform_avg_prices["steam"] == Decimal("19.5")



def test_parse_avg_price_response_rejects_mismatched_market_hash_name() -> None:
    with pytest.raises(ValueError, match="does not match"):
        parse_avg_price_response(
            "A",
            {"success": True, "data": {"marketHashName": "B", "avgPrice": "1", "dataList": []}},
        )



def test_parse_avg_price_response_rejects_non_dict_data() -> None:
    with pytest.raises(ValueError, match="must be a dict"):
        parse_avg_price_response("A", {"success": True, "data": []})



def test_parse_avg_price_response_missing_datalist_returns_empty_platform_prices() -> None:
    result = parse_avg_price_response(
        "A",
        {"success": True, "data": {"marketHashName": "A", "avgPrice": "1"}},
    )
    assert result.platform_avg_prices == {}



def test_parse_avg_price_response_requires_platform() -> None:
    with pytest.raises(ValueError, match="platform"):
        parse_avg_price_response(
            "A",
            {"success": True, "data": {"marketHashName": "A", "avgPrice": "1", "dataList": [{}]}},
        )



def test_parse_base_item_info_response_parses_multiple_items() -> None:
    payload = {
        "success": True,
        "data": [
            {"marketHashName": "A", "name": "A", "platformList": []},
            {"marketHashName": "B", "name": "B", "platformList": []},
        ],
    }

    result = parse_base_item_info_response(payload)

    assert len(result) == 2
    assert result[0].market_hash_name == "A"



def test_parse_base_item_info_response_requires_market_hash_name() -> None:
    with pytest.raises(ValueError, match="marketHashName"):
        parse_base_item_info_response({"success": True, "data": [{"name": "A"}]})



def test_parse_base_item_info_response_preserves_platform_list_in_raw() -> None:
    item = {"marketHashName": "A", "name": "A", "platformList": [{"name": "steam", "itemId": "1"}]}
    result = parse_base_item_info_response({"success": True, "data": [item]})

    assert result[0].raw["platformList"] == item["platformList"]



def test_parse_wear_response_parses_float_and_paint_seed() -> None:
    payload = {
        "success": True,
        "data": {
            "sync": True,
            "success": True,
            "taskId": "task-1",
            "itemPreviewData": {"floatWear": "0.12", "paintseed": 123},
        },
    }

    result = parse_wear_response("steam://inspect/test", payload)

    assert isinstance(result, SteamDTWearParseResult)
    assert result.wear_info.float_value == 0.12
    assert result.wear_info.paint_seed == 123



def test_parse_wear_response_rejects_float_out_of_range() -> None:
    with pytest.raises(ValueError, match="float_value"):
        parse_wear_response(
            "steam://inspect/test",
            {"success": True, "data": {"itemPreviewData": {"floatWear": "1.5"}}},
        )



def test_parse_wear_response_rejects_negative_paint_seed() -> None:
    with pytest.raises(ValueError, match="paint_seed"):
        parse_wear_response(
            "steam://inspect/test",
            {"success": True, "data": {"itemPreviewData": {"paintseed": -1}}},
        )



def test_parse_wear_response_handles_missing_item_preview_data() -> None:
    result = parse_wear_response(
        "steam://inspect/test",
        {"success": True, "data": {"sync": False, "success": False, "taskId": "task-1"}},
    )

    assert result.wear_info.float_value is None
    assert result.sync is False
    assert result.success is False
    assert result.task_id == "task-1"



def test_parse_kline_response_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="docs/STEAMDT_API_NOTES.md"):
        parse_kline_response("A", {"success": True, "data": []})
