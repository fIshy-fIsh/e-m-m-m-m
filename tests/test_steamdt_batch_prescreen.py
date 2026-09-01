"""Phase 16C — Strict SteamDT BUFF batch pre-screen tests."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.clients.steamdt_client import SteamDTBatchPriceResult
from app.services.steamdt_batch_prescreen import (
    PRESCREEN_BATCH_CHUNK_SIZE,
    SteamDTBatchPreScreenDiagnostics,
    SteamDTBatchPreScreenError,
    SteamDTBatchPreScreenRequest,
    SteamDTBatchPreScreenResult,
    build_steamdt_batch_prescreen_resolver,
)


def _platform(
    platform: str,
    *,
    sell: object = "10.00",
    sell_count: object = 1,
    bid: object = None,
) -> dict[str, object]:
    return {
        "platform": platform,
        "platformItemId": "1",
        "sellPrice": sell,
        "sellCount": sell_count,
        "biddingPrice": bid,
        "biddingCount": None,
        "updateTime": 123,
    }


def _result(
    names: list[str],
    *,
    by_name: dict[str, list[dict[str, object]]] | None = None,
) -> SteamDTBatchPriceResult:
    by_name = by_name or {
        name: [_platform("BUFF")] for name in names
    }
    raw = {
        "success": True,
        "data": [
            {"marketHashName": name, "dataList": by_name.get(name, [])}
            for name in names
        ],
    }
    return SteamDTBatchPriceResult(quotes={}, missing=[], raw=raw)


class RecordingTransport:
    def __init__(
        self,
        *,
        by_name: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.by_name = by_name
        self.calls: list[list[str]] = []

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: object = None,
        avg_prices_by_name: object = None,
    ) -> SteamDTBatchPriceResult:
        self.calls.append(list(market_hash_names))
        return _result(market_hash_names, by_name=self.by_name)


def _prescreen(
    names: list[str],
    *,
    by_name: dict[str, list[dict[str, object]]] | None = None,
):
    transport = RecordingTransport(by_name=by_name)
    resolver = build_steamdt_batch_prescreen_resolver(client=transport)
    result = asyncio.run(
        resolver.prescreen(SteamDTBatchPreScreenRequest(market_hash_names=names))
    )
    return result, transport


def test_request_validation() -> None:
    with pytest.raises(SteamDTBatchPreScreenError):
        SteamDTBatchPreScreenRequest(market_hash_names=["ok", " "])
    with pytest.raises(SteamDTBatchPreScreenError):
        SteamDTBatchPreScreenRequest(market_hash_names="not-a-sequence")
    # Empty input is valid and produces an empty result.
    result, transport = _prescreen([])
    assert result.quotes == ()
    assert transport.calls == []


def test_mocked_23_unique_names_chunk_sequentially_10_10_3() -> None:
    names = [f"name{i:02d}" for i in range(23)]
    result, transport = _prescreen(names)
    assert [len(call) for call in transport.calls] == [10, 10, 3]
    assert result.diagnostics.logical_requested_names == 23
    assert result.diagnostics.unique_names == 23
    assert result.diagnostics.duplicates_suppressed == 0
    assert result.diagnostics.chunk_count == 3
    assert result.diagnostics.transport_attempted_names == 23
    assert [quote.market_hash_name for quote in result.quotes] == names


def test_dedupe_preserves_first_seen_order() -> None:
    logical = ["A", "B", "A", "C", "B"]
    result, transport = _prescreen(logical)
    assert transport.calls == [["A", "B", "C"]]
    assert result.requested_market_hash_names == ("A", "B", "C")
    assert result.diagnostics.logical_requested_names == 5
    assert result.diagnostics.unique_names == 3
    assert result.diagnostics.duplicates_suppressed == 2


@pytest.mark.parametrize(
    ("records", "expected_reason"),
    [
        ([], "buff_record_missing"),
        ([_platform("buff")], "buff_record_missing"),
        ([_platform("BUFF", sell=None)], "buff_sell_price_missing"),
        ([_platform("BUFF", sell="0")], "buff_sell_price_non_positive"),
        (
            [_platform("BUFF", sell=None, bid="9")],
            "buff_sell_price_missing",
        ),
        (
            [_platform("STEAM", sell="1")],
            "buff_record_missing",
        ),
        (
            [_platform("BUFF"), _platform("BUFF")],
            "duplicate_buff_records",
        ),
    ],
)
def test_strict_selector_matrix(
    records: list[dict[str, object]], expected_reason: str
) -> None:
    result, _transport = _prescreen(["A"], by_name={"A": records})
    assert result.quotes == ()
    assert result.missing_market_hash_names == ("A",)
    assert result.terminal_selection_failures == (("A", expected_reason),)


def test_strict_buff_positive_sell_selected_with_diagnostics() -> None:
    result, _transport = _prescreen(
        ["A"],
        by_name={
            "A": [
                _platform("STEAM", sell="1"),
                _platform("BUFF", sell="12.34", sell_count=7),
            ]
        },
    )
    [quote] = result.quotes
    assert quote.market_hash_name == "A"
    assert quote.sell_price_cny == Decimal("12.34")
    assert quote.sell_count == 7
    assert quote.update_time == 123
    assert quote.source == "steamdt:buff-prescreen"


def test_response_order_is_logically_deterministic() -> None:
    class ReverseTransport(RecordingTransport):
        async def get_price_batch_with_selection(
            self,
            market_hash_names: list[str],
            *,
            selection_config: object = None,
            avg_prices_by_name: object = None,
        ) -> SteamDTBatchPriceResult:
            self.calls.append(list(market_hash_names))
            return _result(list(reversed(market_hash_names)))

    transport = ReverseTransport()
    resolver = build_steamdt_batch_prescreen_resolver(client=transport)
    result = asyncio.run(
        resolver.prescreen(
            SteamDTBatchPreScreenRequest(market_hash_names=["A", "B", "C"])
        )
    )
    assert [quote.market_hash_name for quote in result.quotes] == ["A", "B", "C"]


def test_duplicate_response_name_fails_whole_chunk_closed() -> None:
    class DuplicateTransport(RecordingTransport):
        async def get_price_batch_with_selection(
            self,
            market_hash_names: list[str],
            *,
            selection_config: object = None,
            avg_prices_by_name: object = None,
        ) -> SteamDTBatchPriceResult:
            raw = _result(market_hash_names).raw
            assert isinstance(raw, dict)
            raw["data"].append(raw["data"][0])  # type: ignore[union-attr]
            return SteamDTBatchPriceResult(quotes={}, missing=[], raw=raw)

    transport = DuplicateTransport()
    resolver = build_steamdt_batch_prescreen_resolver(client=transport)
    result = asyncio.run(
        resolver.prescreen(
            SteamDTBatchPreScreenRequest(market_hash_names=["A", "B"])
        )
    )
    assert result.quotes == ()
    assert result.missing_market_hash_names == ("A", "B")
    assert result.diagnostics.transport_errors == (
        "SteamDTBatchPreScreenError",
    )


def test_unsolicited_response_name_fails_whole_chunk_closed() -> None:
    class ExtraTransport(RecordingTransport):
        async def get_price_batch_with_selection(
            self,
            market_hash_names: list[str],
            *,
            selection_config: object = None,
            avg_prices_by_name: object = None,
        ) -> SteamDTBatchPriceResult:
            return _result([*market_hash_names, "EXTRA"])

    transport = ExtraTransport()
    resolver = build_steamdt_batch_prescreen_resolver(client=transport)
    result = asyncio.run(
        resolver.prescreen(
            SteamDTBatchPreScreenRequest(market_hash_names=["A", "B"])
        )
    )
    assert result.quotes == ()
    assert result.missing_market_hash_names == ("A", "B")


def test_chunk_size_is_frozen_project_value() -> None:
    transport = RecordingTransport()
    assert PRESCREEN_BATCH_CHUNK_SIZE == 10
    with pytest.raises(SteamDTBatchPreScreenError):
        build_steamdt_batch_prescreen_resolver(client=transport, chunk_size=9)
    with pytest.raises(SteamDTBatchPreScreenError):
        build_steamdt_batch_prescreen_resolver(client=transport, chunk_size=11)


def test_diagnostics_and_result_validation() -> None:
    with pytest.raises(SteamDTBatchPreScreenError):
        SteamDTBatchPreScreenDiagnostics(
            logical_requested_names=-1,
            unique_names=0,
            duplicates_suppressed=0,
            chunk_count=0,
            transport_attempted_names=0,
            selected_names=0,
            missing_names=0,
            terminal_selection_failures=0,
            transport_errors=(),
        )
    with pytest.raises(SteamDTBatchPreScreenError):
        SteamDTBatchPreScreenResult(
            requested_market_hash_names=(),
            quotes=(),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=None,  # type: ignore[arg-type]
        )
