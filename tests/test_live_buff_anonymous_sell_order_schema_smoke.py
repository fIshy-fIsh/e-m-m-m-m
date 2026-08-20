from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import socket
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

from scripts import run_live_buff_anonymous_sell_order_schema_smoke as smoke

GOODS_ID = "goods-research-123"
HOSTILE_GOODS_ID = "goods-secret-marker"


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real network is forbidden in offline tests")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


class GuardedEnvironment(Mapping[str, str]):
    def __init__(self, values: dict[str, str], forbidden_keys: set[str]) -> None:
        self._values = values
        self._forbidden_keys = forbidden_keys

    def __getitem__(self, key: str) -> str:
        if key in self._forbidden_keys:
            raise AssertionError(f"forbidden environment read: {key}")
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default=None):
        if key in self._forbidden_keys:
            raise AssertionError(f"forbidden environment read: {key}")
        return self._values.get(key, default)


class FakeRuntime:
    def __init__(
        self,
        response: httpx.Response,
        *,
        state: object | None = None,
        fetch_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.response = response
        self._state = state or smoke.BuffAnonymousSchemaRequestState(
            attempted=1,
            dispatched=1,
            budget_exceeded=False,
        )
        self.fetch_error = fetch_error
        self.close_error = close_error
        self.fetch_calls = 0
        self.close_calls = 0

    @property
    def request_state(self) -> object:
        return self._state

    async def fetch_response(self) -> httpx.Response:
        self.fetch_calls += 1
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.response

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class RaisingStateRuntime(FakeRuntime):
    def __init__(self, response: httpx.Response, error: BaseException) -> None:
        super().__init__(response)
        self.state_error = error

    @property
    def request_state(self) -> object:
        raise self.state_error


class StaticTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        response: httpx.Response | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or _json_response(_valid_payload())
        self.error = error
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(
            self.response.status_code,
            content=self.response.content,
            headers=self.response.headers,
            request=request,
        )

    async def aclose(self) -> None:
        self.closed = True


class DirectControlFlow(BaseException):
    pass


def _enabled_environment(goods_id: str = GOODS_ID) -> dict[str, str]:
    return {
        smoke.RUN_GATE_ENV: "true",
        smoke.GOODS_ID_ENV: goods_id,
    }


def _valid_payload(
    *,
    listing_id: object = "sell-order-private-id",
    price: object = "12.3400",
    paintwear: object = "0.123400",
    assetid: object = "private-asset-id",
    paintseed: object = 456,
    second_item: object | None = None,
) -> dict[str, object]:
    asset_info: dict[str, object] = {"paintwear": paintwear}
    if assetid is not _ABSENT:
        asset_info["assetid"] = assetid
    if paintseed is not _ABSENT:
        asset_info["paintseed"] = paintseed
    items: list[object] = [
        {
            "id": listing_id,
            "price": price,
            "asset_info": asset_info,
            "seller": "private-seller",
            "market_hash_name": "Private Market Name",
        }
    ]
    if second_item is not None:
        items.append(second_item)
    return {
        "code": "OK",
        "data": {"items": items},
        "msg": "private BUFF message",
    }


_ABSENT = object()


def _json_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", "X-Private": "header-secret"},
    )


def _raw_response(content: bytes, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, content=content)


def _run_with_runtime(
    runtime: FakeRuntime,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, list[str], list[str]]:
    output: list[str] = []
    factory_calls: list[str] = []

    async def factory(goods_id: str) -> FakeRuntime:
        factory_calls.append(goods_id)
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment() if environ is None else environ,
            printer=output.append,
            runtime_factory=factory,
        )
    )
    return result, output, factory_calls


def _assert_process_control_identity(
    runtime: FakeRuntime,
    error: BaseException,
) -> None:
    output: list[str] = []

    async def factory(_goods_id: str) -> FakeRuntime:
        return runtime

    try:
        asyncio.run(
            smoke.async_main(
                _enabled_environment(),
                printer=output.append,
                runtime_factory=factory,
            )
        )
    except BaseException as caught:
        assert caught is error
    else:
        raise AssertionError("process-control value should propagate")

    assert runtime.close_calls == 1
    assert output == []


def test_public_contract_is_exact() -> None:
    assert smoke.RUN_GATE_ENV == "BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE"
    assert smoke.GOODS_ID_ENV == "BUFF_READONLY_SMOKE_GOODS_ID"
    assert smoke.BASE_URL == "https://buff.163.com"
    assert smoke.ENDPOINT_PATH == "/api/market/goods/sell_order"
    assert smoke.USER_AGENT == "cs2-tradeup-readonly-schema-smoke/1.0"
    assert inspect.iscoroutinefunction(smoke.async_main)
    assert list(inspect.signature(smoke.async_main).parameters) == [
        "environ",
        "printer",
        "runtime_factory",
    ]


def test_failure_allowlist_is_exact() -> None:
    assert smoke._FAILURE_REASONS == {
        "opt_in_disabled",
        "goods_id_missing",
        "goods_id_invalid",
        "runtime_failed",
        "request_failed",
        "anonymous_access_unavailable",
        "response_not_json",
        "response_schema_invalid",
        "items_missing",
        "no_items",
        "listing_id_missing",
        "price_invalid",
        "paintwear_invalid",
        "request_count_invalid",
        "close_failed",
    }


def test_gate_off_stops_before_goods_id_or_runtime() -> None:
    environ = GuardedEnvironment(
        {},
        {
            smoke.GOODS_ID_ENV,
            "BUFF_API_KEY",
            "BUFF_API_SECRET",
            "COOKIE",
        },
    )
    output: list[str] = []

    async def forbidden_factory(_goods_id: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            environ,
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 0
    assert output == [
        "live_smoke_executed: no",
        "reason: opt_in_disabled",
        "BUFF requests sent: 0",
    ]


@pytest.mark.parametrize("gate", ["", "false", "1", "yes", " true-ish "])
def test_false_like_gate_values_remain_disabled(gate: str) -> None:
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main({smoke.RUN_GATE_ENV: gate}, printer=output.append)
    )

    assert result == 0
    assert output[-1] == "BUFF requests sent: 0"


@pytest.mark.parametrize("gate", ["true", " TRUE ", "TrUe"])
def test_normalized_true_gate_variants_enable_offline(gate: str) -> None:
    runtime = FakeRuntime(_json_response(_valid_payload()))
    environ = {
        smoke.RUN_GATE_ENV: gate,
        smoke.GOODS_ID_ENV: GOODS_ID,
    }

    result, output, _calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert "result: success" in output


@pytest.mark.parametrize("goods_id", [None, "", "   "])
def test_missing_goods_id_stops_before_runtime(goods_id: str | None) -> None:
    values = {smoke.RUN_GATE_ENV: "true"}
    if goods_id is not None:
        values[smoke.GOODS_ID_ENV] = goods_id
    output: list[str] = []

    async def forbidden_factory(_goods_id: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            values,
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: no",
        "reason: goods_id_missing",
        "BUFF requests sent: 0",
    ]


@pytest.mark.parametrize("goods_id", [1, True, object(), ["id"]])
def test_invalid_goods_id_type_stops_before_runtime(goods_id: object) -> None:
    output: list[str] = []

    async def forbidden_factory(_goods_id: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_GATE_ENV: "true",
                smoke.GOODS_ID_ENV: goods_id,  # type: ignore[dict-item]
            },
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: goods_id_invalid" in output
    assert output[-1] == "BUFF requests sent: 0"


def test_goods_id_is_trimmed_and_not_digits_only() -> None:
    runtime = FakeRuntime(_json_response(_valid_payload()))
    environ = _enabled_environment("  alpha-goods-42  ")

    result, _output, factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert factory_calls == ["alpha-goods-42"]


def test_runtime_factory_failure_is_fixed_and_redacted() -> None:
    output: list[str] = []

    async def failing_factory(_goods_id: str):
        raise RuntimeError("goods-secret; Cookie=session; https://private.invalid")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(HOSTILE_GOODS_ID),
            printer=output.append,
            runtime_factory=failing_factory,
        )
    )

    assert result == 1
    assert "reason: runtime_failed" in output
    rendered = "\n".join(output)
    assert HOSTILE_GOODS_ID not in rendered
    assert "RuntimeError" not in rendered
    assert "private.invalid" not in rendered


def test_valid_first_item_success_output_is_exact_and_redacted() -> None:
    runtime = FakeRuntime(_json_response(_valid_payload()))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert runtime.fetch_calls == 1
    assert runtime.close_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: success",
        "anonymous_request: yes",
        "cookie_used: no",
        "login_used: no",
        "page_num: 1",
        "item_list_present: yes",
        "listing_item_present: yes",
        "listing_id_present: yes",
        "price_valid: yes",
        "paintwear_valid: yes",
        "asset_id_present: yes",
        "paintseed_present: yes",
        "BUFF requests sent: 1",
    ]
    rendered = "\n".join(output)
    for forbidden in (
        GOODS_ID,
        "sell-order-private-id",
        "12.3400",
        "0.123400",
        "private-asset-id",
        "456",
        "private-seller",
        "Private Market Name",
        "private BUFF message",
        "header-secret",
        "buff.163.com",
    ):
        assert forbidden not in rendered


def test_optional_asset_id_missing_still_succeeds() -> None:
    runtime = FakeRuntime(
        _json_response(_valid_payload(assetid=_ABSENT))
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "asset_id_present: no" in output
    assert "paintseed_present: yes" in output


def test_optional_paintseed_missing_still_succeeds() -> None:
    runtime = FakeRuntime(
        _json_response(_valid_payload(paintseed=_ABSENT))
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "asset_id_present: yes" in output
    assert "paintseed_present: no" in output


@pytest.mark.parametrize("value", [None, "", 0, False])
def test_optional_null_or_absent_values_report_no(value: object) -> None:
    runtime = FakeRuntime(
        _json_response(_valid_payload(assetid=value, paintseed=value))
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    expected = "no" if value is None else "yes"
    assert f"asset_id_present: {expected}" in output
    assert f"paintseed_present: {expected}" in output


def test_valid_first_item_ignores_hostile_second_item() -> None:
    payload = _valid_payload(
        second_item={
            "id": None,
            "price": "NaN",
            "asset_info": {"paintwear": "Infinity"},
            "Cookie": "second-item-secret",
        }
    )
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "result: success" in output
    assert "second-item-secret" not in "\n".join(output)


def test_invalid_first_item_does_not_fall_forward_to_valid_second() -> None:
    payload = _valid_payload()
    payload["data"] = {
        "items": [
            {"id": None},
            _valid_payload()["data"]["items"][0],  # type: ignore[index]
        ]
    }
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: listing_id_missing" in output


@pytest.mark.parametrize("code", ["ERROR", "ok", None, 0, True])
def test_non_ok_code_is_anonymous_access_unavailable(code: object) -> None:
    payload = _valid_payload()
    payload["code"] = code
    payload["msg"] = "Cookie required; private provider message"
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: anonymous_access_unavailable" in output
    rendered = "\n".join(output)
    assert "Cookie required" not in rendered
    assert "private provider message" not in rendered


@pytest.mark.parametrize(
    "content",
    [b"not-json private-body", b"{", b'{"code":NaN}', b'{"code":"OK","code":"OK"}'],
)
def test_non_json_or_strictly_invalid_json_is_safe(content: bytes) -> None:
    runtime = FakeRuntime(_raw_response(content))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: response_not_json" in output
    assert "private-body" not in "\n".join(output)


@pytest.mark.parametrize("payload", [None, [], "value", 1, True])
def test_valid_json_non_object_is_schema_invalid(payload: object) -> None:
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: response_schema_invalid" in output


@pytest.mark.parametrize("data", [_ABSENT, None, [], "data", 1])
def test_missing_or_wrong_data_is_schema_invalid(data: object) -> None:
    payload: dict[str, object] = {"code": "OK"}
    if data is not _ABSENT:
        payload["data"] = data
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: response_schema_invalid" in output


@pytest.mark.parametrize("items", [_ABSENT, None, {}, "items", 1])
def test_missing_or_wrong_items_is_items_missing(items: object) -> None:
    data: dict[str, object] = {}
    if items is not _ABSENT:
        data["items"] = items
    runtime = FakeRuntime(_json_response({"code": "OK", "data": data}))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: items_missing" in output


def test_empty_items_fails_without_requesting_page_two() -> None:
    runtime = FakeRuntime(
        _json_response({"code": "OK", "data": {"items": []}})
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert runtime.fetch_calls == 1
    assert "reason: no_items" in output


@pytest.mark.parametrize("item", [None, [], "item", 1, True])
def test_non_object_first_item_is_schema_invalid(item: object) -> None:
    runtime = FakeRuntime(
        _json_response({"code": "OK", "data": {"items": [item]}})
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: response_schema_invalid" in output


@pytest.mark.parametrize(
    "listing_id",
    [_ABSENT, None, "", "  ", -1, 0, 123456, True, 1.0, [], {}],
)
def test_missing_or_invalid_listing_id_fails(listing_id: object) -> None:
    payload = _valid_payload()
    item = payload["data"]["items"][0]  # type: ignore[index]
    if listing_id is _ABSENT:
        del item["id"]  # type: ignore[index]
    else:
        item["id"] = listing_id  # type: ignore[index]
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: listing_id_missing" in output


def test_compatible_string_listing_id_succeeds() -> None:
    listing_id = "order-private-unique"
    runtime = FakeRuntime(
        _json_response(_valid_payload(listing_id=listing_id))
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "listing_id_present: yes" in output
    assert listing_id not in "\n".join(output)


@pytest.mark.parametrize("price", ["12.3400", 12, 12.5, "1E+2"])
def test_valid_decimal_price_forms_succeed_without_output(price: object) -> None:
    runtime = FakeRuntime(_json_response(_valid_payload(price=price)))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "price_valid: yes" in output
    assert str(price) not in "\n".join(output)


@pytest.mark.parametrize(
    "price",
    [_ABSENT, None, "", " 1 ", "bad", "0", 0, "-1", -1, "NaN", "Infinity", True, [], {}],
)
def test_invalid_nonpositive_or_nonfinite_price_fails(price: object) -> None:
    payload = _valid_payload()
    item = payload["data"]["items"][0]  # type: ignore[index]
    if price is _ABSENT:
        del item["price"]  # type: ignore[index]
    else:
        item["price"] = price  # type: ignore[index]
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: price_invalid" in output


@pytest.mark.parametrize("paintwear", ["0", "1", 0, 1, "0.123400", 0.5, "1E-3"])
def test_valid_paintwear_forms_and_boundaries_succeed(paintwear: object) -> None:
    runtime = FakeRuntime(
        _json_response(_valid_payload(paintwear=paintwear))
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 0
    assert "paintwear_valid: yes" in output
    if str(paintwear) not in {"0", "1"}:
        assert str(paintwear) not in "\n".join(output)


@pytest.mark.parametrize(
    "paintwear",
    [_ABSENT, None, "", " 0.5 ", "bad", "-0.1", -1, "1.1", 2, "NaN", "Infinity", True, [], {}],
)
def test_invalid_out_of_range_or_nonfinite_paintwear_fails(
    paintwear: object,
) -> None:
    payload = _valid_payload()
    item = payload["data"]["items"][0]  # type: ignore[index]
    asset_info = item["asset_info"]  # type: ignore[index]
    if paintwear is _ABSENT:
        del asset_info["paintwear"]  # type: ignore[index]
    else:
        asset_info["paintwear"] = paintwear  # type: ignore[index]
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: paintwear_invalid" in output


@pytest.mark.parametrize("asset_info", [_ABSENT, None, [], "asset", 1])
def test_missing_or_invalid_asset_info_is_paintwear_invalid(
    asset_info: object,
) -> None:
    payload = _valid_payload()
    item = payload["data"]["items"][0]  # type: ignore[index]
    if asset_info is _ABSENT:
        del item["asset_info"]  # type: ignore[index]
    else:
        item["asset_info"] = asset_info  # type: ignore[index]
    runtime = FakeRuntime(_json_response(payload))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: paintwear_invalid" in output


@pytest.mark.parametrize("status_code", [302, 401, 403, 429, 500])
def test_http_failure_is_fixed_and_never_retried(status_code: int) -> None:
    runtime = FakeRuntime(_raw_response(b"private BUFF body", status_code=status_code))

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert runtime.fetch_calls == 1
    assert "reason: request_failed" in output
    assert "private BUFF body" not in "\n".join(output)


def test_ordinary_transport_failure_is_fixed_and_redacted() -> None:
    runtime = FakeRuntime(
        _raw_response(b"unused"),
        fetch_error=httpx.ConnectError(
            "Cookie secret; goods-secret; https://private.invalid"
        ),
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert runtime.fetch_calls == 1
    assert "reason: request_failed" in output
    rendered = "\n".join(output)
    assert "ConnectError" not in rendered
    assert "goods-secret" not in rendered
    assert "private.invalid" not in rendered


@pytest.mark.parametrize(
    "state",
    [
        smoke.BuffAnonymousSchemaRequestState(  # type: ignore[call-arg]
            attempted=0,
            dispatched=0,
            budget_exceeded=False,
        ),
        smoke.BuffAnonymousSchemaRequestState(  # type: ignore[call-arg]
            attempted=2,
            dispatched=1,
            budget_exceeded=True,
        ),
        smoke.BuffAnonymousSchemaRequestState(  # type: ignore[call-arg]
            attempted=1,
            dispatched=0,
            budget_exceeded=False,
        ),
        object(),
    ],
)
def test_invalid_success_request_state_fails_closed(state: object) -> None:
    runtime = FakeRuntime(_json_response(_valid_payload()), state=state)

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert "result: success" not in output


def test_budget_violation_overrides_ordinary_request_failure() -> None:
    runtime = FakeRuntime(
        _raw_response(b"unused"),
        state=smoke.BuffAnonymousSchemaRequestState(
            attempted=2,
            dispatched=1,
            budget_exceeded=True,
        ),
        fetch_error=RuntimeError("ordinary"),
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "BUFF requests sent: 1"


def test_raising_ordinary_request_state_is_unavailable_and_redacted() -> None:
    runtime = RaisingStateRuntime(
        _json_response(_valid_payload()),
        RuntimeError("state Cookie secret"),
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "BUFF requests sent: unavailable"
    assert "state Cookie secret" not in "\n".join(output)


def test_close_failure_replaces_success_without_partial_output() -> None:
    runtime = FakeRuntime(
        _json_response(_valid_payload()),
        close_error=RuntimeError("close Cookie secret"),
    )

    result, output, _calls = _run_with_runtime(runtime)

    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: close_failed",
        "BUFF requests sent: 1",
    ]
    assert runtime.close_calls == 1


@pytest.mark.parametrize(
    "error",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancel"),
        KeyboardInterrupt(),
        SystemExit(7),
        DirectControlFlow("stop"),
    ],
)
def test_process_control_from_request_propagates_after_cleanup(
    error: BaseException,
) -> None:
    runtime = FakeRuntime(_raw_response(b"unused"), fetch_error=error)
    _assert_process_control_identity(runtime, error)


@pytest.mark.parametrize(
    "error",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancel"),
        KeyboardInterrupt(),
        SystemExit(8),
    ],
)
def test_request_state_process_control_propagates_after_cleanup(
    error: BaseException,
) -> None:
    runtime = RaisingStateRuntime(_json_response(_valid_payload()), error)
    _assert_process_control_identity(runtime, error)


def test_printer_failure_occurs_after_cleanup() -> None:
    runtime = FakeRuntime(_json_response(_valid_payload()))

    async def factory(_goods_id: str) -> FakeRuntime:
        return runtime

    def failing_printer(_message: str) -> None:
        assert runtime.close_calls == 1
        raise RuntimeError("printer failed")

    with pytest.raises(RuntimeError, match="printer failed"):
        asyncio.run(
            smoke.async_main(
                _enabled_environment(),
                printer=failing_printer,
                runtime_factory=factory,
            )
        )


def test_real_runtime_request_is_exact_anonymous_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport()
    original_async_client = httpx.AsyncClient
    client_kwargs: list[dict[str, object]] = []

    def http_factory(*args: object, **kwargs: object):
        client_kwargs.append(dict(kwargs))
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(_enabled_environment(), printer=output.append)
    )

    assert result == 0
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "buff.163.com"
    assert request.url.path == "/api/market/goods/sell_order"
    assert list(request.url.params.multi_items()) == [
        ("game", "csgo"),
        ("goods_id", GOODS_ID),
        ("page_num", "1"),
        ("sort_by", "default"),
    ]
    assert request.content == b""
    assert request.headers["User-Agent"] == smoke.USER_AGENT
    assert request.headers["Accept"] == "application/json"
    sensitive = {
        "cookie",
        "authorization",
        "proxy-authorization",
        "device-id",
        "x-csrftoken",
        "referer",
        "origin",
        "x-requested-with",
    }
    assert not sensitive.intersection(name.casefold() for name in request.headers)
    assert client_kwargs[0]["follow_redirects"] is False
    assert client_kwargs[0]["trust_env"] is False
    assert transport.closed is True
    assert output[-1] == "BUFF requests sent: 1"
    for forbidden_query in (
        "page_size",
        "min_paintwear",
        "max_paintwear",
        "min_paintseed",
        "max_paintseed",
        "price.asc",
        "price.desc",
        "filter",
        "search",
    ):
        assert forbidden_query not in request.url.params


def test_real_runtime_transport_error_attempts_once_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport(
        error=httpx.ConnectError("private transport failure")
    )
    original_async_client = httpx.AsyncClient

    def http_factory(*args: object, **kwargs: object):
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(_enabled_environment(), printer=output.append)
    )

    assert result == 1
    assert len(transport.requests) == 1
    assert transport.closed is True
    assert "reason: request_failed" in output


def test_second_real_request_is_blocked_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport()
    original_async_client = httpx.AsyncClient

    def http_factory(*args: object, **kwargs: object):
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    runtime = asyncio.run(smoke._create_http_smoke_runtime(GOODS_ID))
    try:
        asyncio.run(runtime.fetch_response())
        with pytest.raises(RuntimeError):
            asyncio.run(runtime.fetch_response())
    finally:
        asyncio.run(runtime.aclose())

    assert len(transport.requests) == 1
    assert runtime.request_state == smoke.BuffAnonymousSchemaRequestState(
        attempted=2,
        dispatched=1,
        budget_exceeded=True,
    )
    assert transport.closed is True


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_entrypoints_are_zero_network_safe(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env[smoke.GOODS_ID_ENV] = "entrypoint-private-goods"
    env["BUFF_API_KEY"] = "entrypoint-private-key"
    env["BUFF_API_SECRET"] = "entrypoint-private-secret"
    env["HTTPS_PROXY"] = "https://must-not-connect.invalid"
    command = (
        [sys.executable, "scripts/run_live_buff_anonymous_sell_order_schema_smoke.py"]
        if entrypoint == "direct"
        else [
            sys.executable,
            "-m",
            "scripts.run_live_buff_anonymous_sell_order_schema_smoke",
        ]
    )

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "reason: opt_in_disabled" in result.stdout
    assert "BUFF requests sent: 0" in result.stdout
    assert "entrypoint-private" not in result.stdout
    assert "must-not-connect.invalid" not in result.stdout


def test_script_has_only_anonymous_readonly_schema_probe_architecture() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "scripts" / "run_live_buff_anonymous_sell_order_schema_smoke.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr.casefold())
            elif isinstance(node.func, ast.Name):
                calls.append(node.func.id.casefold())

    forbidden_imports = {
        "buff_client",
        "app.config",
        "dotenv",
        "app.clients.steamdt",
        "steamapis",
        "redis",
        "cache",
        "scheduler",
        "discord",
        "fastapi",
        "database",
        "playwright",
        "selenium",
        "webbrowser",
        "requests",
        "aiohttp",
    }
    forbidden_calls = {
        "post",
        "put",
        "patch",
        "delete",
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
        "to_thread",
        "popen",
        "eval",
        "exec",
        "compile",
        "__import__",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_imports
    )
    assert not forbidden_calls.intersection(calls)
    client_get_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_client"
    ]
    assert len(client_get_calls) == 1
    assert "random" not in imports
    assert "retry" not in source.casefold()
    assert "backoff" not in source.casefold()
    assert "page_size" not in source
    assert "min_paintwear" not in source
    assert "max_paintwear" not in source
    assert "min_paintseed" not in source
    assert "max_paintseed" not in source
    assert "price.asc" not in source
    assert "price.desc" not in source
    assert not any(
        isinstance(node, (ast.AsyncFor, ast.While)) for node in ast.walk(tree)
    )
    assert source.count("follow_redirects=False") == 1
    assert source.count("trust_env=False") == 1


def test_no_sensitive_behavior_is_constructed_or_emitted() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_live_buff_anonymous_sell_order_schema_smoke.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden_calls = {
        "login",
        "buy",
        "purchase",
        "preview",
        "captcha",
        "cloudflare",
        "webdriver",
        "cookiejar",
    }
    assert not forbidden_calls.intersection(called_names)
    assert "BUFF_API_KEY" not in source
    assert "BUFF_API_SECRET" not in source
    assert "Device-Id:" not in source
    assert "X-Requested-With:" not in source
    assert "proxy=" not in source


def test_protected_modules_do_not_reverse_import_smoke() -> None:
    project_root = Path(__file__).resolve().parents[1]
    smoke_name = "run_live_buff_anonymous_sell_order_schema_smoke"
    protected = [
        project_root / "app" / "clients" / "buff_client.py",
        project_root / "app" / "services" / "buff_listing.py",
        project_root / "app" / "services" / "buff_listing_parser.py",
        project_root / "app" / "services" / "buff_listing_eligibility.py",
        project_root / "app" / "services" / "buff_listing_qualification.py",
        project_root / "app" / "services" / "buff_listing_solver_adapter.py",
        project_root / "app" / "services" / "market_scan_service.py",
        project_root / "app" / "services" / "recipe_solver.py",
        project_root / "app" / "services" / "tradeup_engine.py",
    ]

    for path in protected:
        assert smoke_name not in path.read_text(encoding="utf-8")


def test_env_example_declares_exact_controls_once() -> None:
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8"
    )

    assert env_example.count(
        "BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE=false"
    ) == 1
    assert env_example.count("BUFF_READONLY_SMOKE_GOODS_ID=") == 1


def test_socket_guard_proves_real_network_is_blocked() -> None:
    with pytest.raises(AssertionError, match="real network is forbidden"):
        socket.getaddrinfo("buff.163.com", 443)
