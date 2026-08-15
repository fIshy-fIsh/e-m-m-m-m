import ast
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from scripts import run_live_steamdt_market_smoke as smoke

ITEM = "AK-47 | Redline (Field-Tested)"


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


class FakeClient:
    def __init__(
        self,
        quotes: list[SteamDTPlatformPrice],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.quotes = quotes
        self.error = error
        self.calls: list[str] = []

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        self.calls.append(market_hash_name)
        if self.error is not None:
            raise self.error
        return self.quotes


class FakeRuntime:
    def __init__(
        self,
        client: FakeClient,
        *,
        request_count: object = 1,
        close_error: BaseException | None = None,
    ) -> None:
        self.client = client
        self._request_count = request_count
        self.close_error = close_error
        self.close_calls = 0

    @property
    def request_count(self) -> object:
        return self._request_count

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def _quote(
    platform: str = "BUFF163",
    *,
    platform_item_id: str | None = "opaque-id",
    sell_price: str | None = "12.3400",
    sell_count: int | None = 2,
    bidding_price: str | None = "11.11",
    bidding_count: int | None = 1,
    update_time: int | str | None = 123456,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=platform_item_id,
        sell_price_cny=None if sell_price is None else Decimal(sell_price),
        sell_count=sell_count,
        bidding_price_cny=(
            None if bidding_price is None else Decimal(bidding_price)
        ),
        bidding_count=bidding_count,
        update_time=update_time,
        raw=raw,
    )


def _enabled_environment(secret: str = "dummy-secret") -> dict[str, str]:
    return {
        smoke.RUN_GATE_ENV: "true",
        smoke.API_KEY_ENV: secret,
        smoke.MARKET_HASH_NAME_ENV: f" {ITEM} ",
        smoke.BASE_URL_ENV: "https://example.invalid",
    }


def _run_with_runtime(
    runtime: FakeRuntime,
    *,
    environ: dict[str, str] | None = None,
) -> tuple[int, list[str], list[tuple[str, str]]]:
    output: list[str] = []
    factory_calls: list[tuple[str, str]] = []

    async def factory(base_url: str, api_key: str) -> FakeRuntime:
        factory_calls.append((base_url, api_key))
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment() if environ is None else environ,
            printer=output.append,
            runtime_factory=factory,
        )
    )
    return result, output, factory_calls


def test_default_disabled_exits_before_key_item_base_url_or_runtime_access() -> None:
    environ = GuardedEnvironment(
        {},
        {
            smoke.API_KEY_ENV,
            smoke.MARKET_HASH_NAME_ENV,
            smoke.BASE_URL_ENV,
        },
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
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
        "SteamDT requests sent: 0",
    ]


@pytest.mark.parametrize("gate", ["false", "1", "yes", " true-ish ", ""])
def test_only_explicit_true_enables_the_existing_gate(gate: str) -> None:
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            {smoke.RUN_GATE_ENV: gate},
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 0
    assert output[-1] == "SteamDT requests sent: 0"


@pytest.mark.parametrize("gate", ["true", " TRUE ", "TrUe"])
def test_normalized_true_variants_enable_the_existing_gate(gate: str) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]))
    environ = _enabled_environment()
    environ[smoke.RUN_GATE_ENV] = gate

    result, output, _factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert "result: success" in output


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_or_blank_key_exits_before_item_base_url_or_runtime(
    key: str | None,
) -> None:
    values = {smoke.RUN_GATE_ENV: "true"}
    if key is not None:
        values[smoke.API_KEY_ENV] = key
    environ = GuardedEnvironment(
        values,
        {smoke.MARKET_HASH_NAME_ENV, smoke.BASE_URL_ENV},
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            environ,
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: no",
        "reason: api_key_missing",
        "SteamDT requests sent: 0",
    ]


@pytest.mark.parametrize("item", [None, "", "   "])
def test_missing_or_blank_item_exits_before_base_url_or_runtime(
    item: str | None,
) -> None:
    values = {smoke.RUN_GATE_ENV: "true", smoke.API_KEY_ENV: "secret"}
    if item is not None:
        values[smoke.MARKET_HASH_NAME_ENV] = item
    environ = GuardedEnvironment(values, {smoke.BASE_URL_ENV})
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            environ,
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: no",
        "reason: market_hash_name_missing",
        "SteamDT requests sent: 0",
    ]


def test_enabled_smoke_trims_key_and_item_and_calls_one_client_once() -> None:
    secret = "trimmed-secret"
    client = FakeClient([_quote()])
    runtime = FakeRuntime(client)
    environ = _enabled_environment(secret)
    environ[smoke.API_KEY_ENV] = f"  {secret}  "

    result, output, factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert factory_calls == [("https://example.invalid", secret)]
    assert client.calls == [ITEM]
    assert runtime.close_calls == 1
    assert output[-1] == "SteamDT requests sent: 1"


def test_success_preserves_provider_order_and_prints_only_allowlisted_aggregates() -> None:
    secret = "never-print-secret"
    raw = {"Authorization": f"Bearer {secret}", "raw_payload": "private"}
    runtime = FakeRuntime(
        FakeClient(
            [
                _quote("网易BUFF", raw=raw),
                _quote(
                    "buff",
                    platform_item_id=None,
                    sell_price=None,
                    sell_count=None,
                    bidding_price=None,
                    bidding_count=None,
                    update_time=None,
                    raw=raw,
                ),
            ]
        )
    )

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    rendered = "\n".join(output)
    assert result == 0
    assert output[:4] == [
        "live_smoke_executed: yes",
        "result: success",
        "market_hash_name_requested: yes",
        "platform_count: 2",
    ]
    first_platform = f"platform: {json.dumps('网易BUFF')}"
    assert output.index(first_platform) < output.index('platform: "buff"')
    assert "platform_item_id_present: yes" in output
    assert "platform_item_id_present: no" in output
    assert "sell_price_cny: 12.3400" in output
    assert "sell_price_cny: missing" in output
    assert "sell_count: 2" in output
    assert "sell_count: missing" in output
    assert "bidding_price_cny: 11.11" in output
    assert "bidding_price_cny: missing" in output
    assert "update_time_present: yes" in output
    assert "update_time_present: no" in output
    assert ITEM not in rendered
    assert "opaque-id" not in rendered
    assert "123456" not in rendered
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "raw_payload" not in rendered


def test_external_platform_is_json_escaped_and_secret_redacted() -> None:
    secret = "platform-secret"
    platform = f"BUFF\nAuthorization: Bearer {secret}"
    runtime = FakeRuntime(FakeClient([_quote(platform)]))

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    rendered = "\n".join(output)
    assert result == 0
    assert "\\n" in rendered
    assert secret not in rendered
    assert "Authorization:" not in rendered
    assert "\nAuthorization:" not in rendered


def test_empty_platform_result_is_failure_without_retry() -> None:
    client = FakeClient([])
    runtime = FakeRuntime(client)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert client.calls == [ITEM]
    assert runtime.close_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: no_platform_records",
        "SteamDT requests sent: 1",
    ]


@pytest.mark.parametrize("request_count", [0, 2])
def test_request_count_other_than_one_fails(request_count: int) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]), request_count=request_count)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == f"SteamDT requests sent: {request_count}"
    assert not any(line.startswith("platform:") for line in output)


@pytest.mark.parametrize("request_count", [True, 1.0, -1])
def test_invalid_request_counter_is_redacted_failure(request_count: object) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]), request_count=request_count)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: market_data_failed" in output
    assert "error_type: TypeError" in output
    assert output[-1] == "SteamDT requests sent: unavailable"


class RaisingRequestCountRuntime(FakeRuntime):
    @property
    def request_count(self) -> int:
        raise RuntimeError("counter leaked secret")


def test_raising_request_counter_does_not_leak_message() -> None:
    runtime = RaisingRequestCountRuntime(FakeClient([_quote()]))

    result, output, _factory_calls = _run_with_runtime(runtime)

    rendered = "\n".join(output)
    assert result == 1
    assert "error_type: RuntimeError" in output
    assert "counter leaked" not in rendered
    assert output[-1] == "SteamDT requests sent: unavailable"


def test_client_failure_is_redacted_and_runtime_closes() -> None:
    secret = "failure-secret"
    runtime = FakeRuntime(
        FakeClient(
            [],
            error=RuntimeError(f"Authorization: Bearer {secret}; raw response"),
        )
    )

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    rendered = "\n".join(output)
    assert result == 1
    assert "reason: market_data_failed" in output
    assert "error_type: RuntimeError" in output
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "raw response" not in rendered
    assert runtime.close_calls == 1


def test_close_failure_replaces_success_without_partial_platform_output() -> None:
    secret = "close-secret"
    runtime = FakeRuntime(
        FakeClient([_quote()]),
        close_error=RuntimeError(f"close leaked {secret}"),
    )

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    rendered = "\n".join(output)
    assert result == 1
    assert "reason: close_failed" in output
    assert "error_type: RuntimeError" in output
    assert not any(line.startswith("platform:") for line in output)
    assert secret not in rendered
    assert runtime.close_calls == 1


@pytest.mark.parametrize(
    "error",
    [MemoryError(), asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(9)],
)
def test_process_control_values_propagate_after_runtime_cleanup(
    error: BaseException,
) -> None:
    runtime = FakeRuntime(FakeClient([], error=error))

    with pytest.raises(type(error)):
        _run_with_runtime(runtime)

    assert runtime.close_calls == 1


def test_printer_failure_occurs_after_runtime_cleanup() -> None:
    runtime = FakeRuntime(FakeClient([_quote()]))

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    def failing_printer(_message: str) -> None:
        raise RuntimeError("printer failed")

    with pytest.raises(RuntimeError, match="printer failed"):
        asyncio.run(
            smoke.async_main(
                _enabled_environment(),
                printer=failing_printer,
                runtime_factory=factory,
            )
        )

    assert runtime.close_calls == 1


class StaticTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.payload)

    async def aclose(self) -> None:
        self.closed = True


def test_real_runtime_uses_one_single_request_max_retries_zero_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport(
        200,
        {
            "success": True,
            "data": [
                {
                    "platform": "BUFF",
                    "platformItemId": "private-id",
                    "sellPrice": "12.34",
                    "sellCount": 2,
                    "biddingPrice": "11.11",
                    "biddingCount": 1,
                    "updateTime": 123,
                }
            ],
        },
    )
    original_async_client = httpx.AsyncClient
    captured_configs: list[object] = []
    original_client = smoke.SteamDTHttpClient

    def http_factory(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        return original_async_client(*args, transport=transport, **kwargs)

    def client_factory(config, *args, **kwargs):
        captured_configs.append(config)
        return original_client(config, *args, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", client_factory)
    output: list[str] = []

    result = asyncio.run(smoke.async_main(_enabled_environment(), printer=output.append))

    assert result == 0
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/open/cs2/v1/price/single"
    assert request.url.params["marketHashName"] == ITEM
    assert len(captured_configs) == 1
    assert captured_configs[0].max_retries == 0
    assert captured_configs[0].dry_run is False
    assert transport.closed is True
    assert output[-1] == "SteamDT requests sent: 1"


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_type"),
    [
        (500, {"success": False}, "SteamDTHttpStatusError"),
        (429, {"success": False}, "SteamDTRateLimitError"),
        (200, ["raw"], "SteamDTResponseParseError"),
    ],
)
def test_real_runtime_failure_never_retries(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: object,
    expected_type: str,
) -> None:
    transport = StaticTransport(status_code, payload)
    original_async_client = httpx.AsyncClient

    def http_factory(*args, **kwargs):
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    output: list[str] = []

    result = asyncio.run(smoke.async_main(_enabled_environment(), printer=output.append))

    assert result == 1
    assert len(transport.requests) == 1
    assert transport.closed is True
    assert f"error_type: {expected_type}" in output
    assert output[-1] == "SteamDT requests sent: 1"


class TrackedHttpClient:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def test_runtime_construction_failure_closes_owned_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client = TrackedHttpClient()

    def http_factory(**_kwargs):
        return http_client

    def failing_client(*_args, **_kwargs):
        raise RuntimeError("construction failed")

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", failing_client)

    with pytest.raises(RuntimeError, match="construction failed"):
        asyncio.run(
            smoke._create_http_smoke_runtime(
                "https://example.invalid",
                "secret",
            )
        )

    assert http_client.close_calls == 1


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_direct_and_module_entrypoints_are_zero_network_safe(
    entrypoint: str,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env[smoke.API_KEY_ENV] = "entrypoint-secret"
    env[smoke.MARKET_HASH_NAME_ENV] = ITEM
    env[smoke.BASE_URL_ENV] = "https://must-not-connect.invalid"
    env["REDIS_URL"] = "redis://must-not-connect.invalid/15"
    command = (
        [sys.executable, "scripts/run_live_steamdt_market_smoke.py"]
        if entrypoint == "direct"
        else [sys.executable, "-m", "scripts.run_live_steamdt_market_smoke"]
    )

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0
    assert "live_smoke_executed: no" in combined
    assert "reason: opt_in_disabled" in combined
    assert "SteamDT requests sent: 0" in combined
    assert "entrypoint-secret" not in combined
    assert "must-not-connect.invalid" not in combined


def test_smoke_has_no_forbidden_endpoint_or_runtime_architecture() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_live_steamdt_market_smoke.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called_attributes.add(node.func.attr.casefold())

    forbidden_imports = {
        "redis",
        "cache",
        "price_provider",
        "valuation",
        "steamapis",
        "buff",
        "pipeline",
        "scheduler",
        "fastapi",
        "discord",
        "app.config",
    }
    forbidden_calls = {
        "get_price_batch",
        "get_base_item_info",
        "get_avg_price",
        "get_kline",
        "get_wear_info",
        "create_task",
        "gather",
        "sleep",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_imports
    )
    assert called_attributes.isdisjoint(forbidden_calls)
    assert "purchase" not in source.casefold()
    assert "listing_id" not in source
    assert "max_retries=0" in source
    assert source.count("get_steamdt_market_data(") == 1
