import ast
import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from scripts import run_live_steamdt_buff_price_provider_smoke as smoke

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


class RaisingRequestCountRuntime(FakeRuntime):
    def __init__(self, client: FakeClient, error: BaseException) -> None:
        super().__init__(client)
        self.counter_error = error

    @property
    def request_count(self) -> int:
        raise self.counter_error


def _quote(
    platform: str = "BUFF",
    *,
    platform_item_id: str | None = "opaque-platform-id",
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


def _tampered_sell_quote(value: Decimal) -> SteamDTPlatformPrice:
    quote = _quote()
    object.__setattr__(quote, "sell_price_cny", value)
    return quote


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


def test_public_environment_contract_is_exact() -> None:
    assert smoke.RUN_GATE_ENV == "STEAMDT_RUN_BUFF_PROVIDER_SMOKE"
    assert smoke.API_KEY_ENV == "STEAMDT_API_KEY"
    assert smoke.MARKET_HASH_NAME_ENV == "STEAMDT_SMOKE_MARKET_HASH_NAME"
    assert smoke.BASE_URL_ENV == "STEAMDT_BASE_URL"
    assert smoke.DEFAULT_BASE_URL == "https://open.steamdt.com"


def test_default_disabled_exits_before_key_name_base_url_or_runtime_access() -> None:
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
def test_only_normalized_explicit_true_enables_gate(gate: str) -> None:
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
def test_normalized_true_variants_enable_gate(gate: str) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]))
    environ = _enabled_environment()
    environ[smoke.RUN_GATE_ENV] = gate

    result, output, _factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert "result: success" in output


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_exits_before_name_base_url_or_runtime(key: str | None) -> None:
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


@pytest.mark.parametrize("name", [None, "", "   "])
def test_missing_name_exits_before_base_url_or_runtime(name: str | None) -> None:
    values = {smoke.RUN_GATE_ENV: "true", smoke.API_KEY_ENV: "secret"}
    if name is not None:
        values[smoke.MARKET_HASH_NAME_ENV] = name
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


def test_enabled_smoke_trims_key_and_name_and_calls_client_once() -> None:
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
    assert output == [
        "live_smoke_executed: yes",
        "result: success",
        "market_hash_name_requested: yes",
        "source: steamdt:buff",
        "price_quote_present: yes",
        "price_cny: 12.3400",
        "SteamDT requests sent: 1",
    ]


def test_default_base_url_is_read_only_after_all_guards() -> None:
    environ = _enabled_environment()
    del environ[smoke.BASE_URL_ENV]
    runtime = FakeRuntime(FakeClient([_quote()]))

    result, _output, factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert factory_calls == [(smoke.DEFAULT_BASE_URL, "dummy-secret")]


def test_real_provider_uses_exact_buff_sell_not_bid_or_other_platforms() -> None:
    raw = {"Authorization": "Bearer raw-secret", "raw_response": "private"}
    client = FakeClient(
        [
            _quote("STEAM", sell_price="9999", bidding_price="99999", raw=raw),
            _quote("YOUPIN", sell_price="8888", bidding_price="88888", raw=raw),
            _quote("C5", sell_price="7777", bidding_price="77777", raw=raw),
            _quote("HALOSKINS", sell_price="6666", bidding_price="66666", raw=raw),
            _quote("BUFF", sell_price="12.3400", bidding_price="999999", raw=raw),
        ]
    )
    runtime = FakeRuntime(client)

    result, output, _factory_calls = _run_with_runtime(runtime)

    rendered = "\n".join(output)
    assert result == 0
    assert client.calls == [ITEM]
    assert "price_cny: 12.3400" in output
    assert "source: steamdt:buff" in output
    assert "999999" not in rendered
    assert "9999" not in rendered
    assert "raw-secret" not in rendered
    assert "raw_response" not in rendered
    assert "opaque-platform-id" not in rendered
    assert "123456" not in rendered
    assert ITEM not in rendered


@pytest.mark.parametrize(
    ("quotes", "reason"),
    [
        ([], "buff_record_missing"),
        ([_quote("STEAM", sell_price="999999")], "buff_record_missing"),
        ([_quote("buff"), _quote("BUFF163")], "buff_record_missing"),
        ([_quote(), _quote()], "duplicate_buff_records"),
        ([_quote(sell_price=None, bidding_price="999999")], "buff_sell_price_missing"),
        ([_tampered_sell_quote(Decimal("NaN"))], "price_provider_failed"),
        ([_tampered_sell_quote(Decimal("Infinity"))], "buff_sell_price_non_finite"),
        ([_quote(sell_price="0", bidding_price="999999")], "buff_sell_price_non_positive"),
        ([_tampered_sell_quote(Decimal("-1"))], "price_provider_failed"),
    ],
)
def test_selection_failures_are_allowlisted_and_never_fallback(
    quotes: list[SteamDTPlatformPrice],
    reason: str,
) -> None:
    client = FakeClient(quotes)
    runtime = FakeRuntime(client)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert client.calls == [ITEM]
    assert runtime.close_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        f"reason: {reason}",
        "SteamDT requests sent: 1",
    ]


def test_ordinary_provider_failure_is_fixed_and_redacted() -> None:
    secret = "provider-secret"
    hostile_name = "Name\nAuthorization: Bearer provider-secret"
    runtime = FakeRuntime(
        FakeClient(
            [],
            error=RuntimeError(
                f"{hostile_name}; raw response; opaque-id; https://purchase.invalid"
            ),
        )
    )
    environ = _enabled_environment(secret)
    environ[smoke.MARKET_HASH_NAME_ENV] = hostile_name

    result, output, _factory_calls = _run_with_runtime(runtime, environ=environ)

    rendered = "\n".join(output)
    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: price_provider_failed",
        "SteamDT requests sent: 1",
    ]
    for forbidden in (
        secret,
        hostile_name,
        "Authorization",
        "raw response",
        "opaque-id",
        "purchase.invalid",
        "RuntimeError",
    ):
        assert forbidden not in rendered
    assert runtime.close_calls == 1


@pytest.mark.parametrize("request_count", [0, 2])
def test_request_count_other_than_one_fails(request_count: int) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]), request_count=request_count)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == f"SteamDT requests sent: {request_count}"
    assert "price_cny: 12.3400" not in output


@pytest.mark.parametrize("request_count", [True, 1.0, -1])
def test_invalid_request_counter_is_unavailable_and_fail_closed(
    request_count: object,
) -> None:
    runtime = FakeRuntime(FakeClient([_quote()]), request_count=request_count)

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: unavailable"


def test_raising_request_counter_does_not_leak_message() -> None:
    runtime = RaisingRequestCountRuntime(
        FakeClient([_quote()]),
        RuntimeError("counter leaked Authorization: Bearer secret"),
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    rendered = "\n".join(output)
    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: unavailable"
    assert "counter leaked" not in rendered
    assert "RuntimeError" not in rendered


def test_more_than_one_request_takes_precedence_over_provider_failure() -> None:
    runtime = FakeRuntime(
        FakeClient([], error=RuntimeError("ordinary")),
        request_count=2,
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: 2"


def test_close_failure_replaces_success_without_partial_quote_output() -> None:
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
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: close_failed",
        "SteamDT requests sent: 1",
    ]
    assert "price_cny:" not in rendered
    assert secret not in rendered
    assert runtime.close_calls == 1


class DirectControlFlow(BaseException):
    pass


@pytest.mark.parametrize(
    "error",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancel"),
        KeyboardInterrupt(),
        SystemExit(9),
        DirectControlFlow("stop"),
    ],
)
def test_process_control_values_propagate_by_identity_after_cleanup(
    error: BaseException,
) -> None:
    runtime = FakeRuntime(FakeClient([], error=error))
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
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


@pytest.mark.parametrize(
    "error",
    [MemoryError("memory"), asyncio.CancelledError("cancel"), KeyboardInterrupt(), SystemExit(4)],
)
def test_request_counter_process_control_propagates_by_identity(
    error: BaseException,
) -> None:
    runtime = RaisingRequestCountRuntime(FakeClient([_quote()]), error)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
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


def test_printer_failure_occurs_after_runtime_cleanup() -> None:
    runtime = FakeRuntime(FakeClient([_quote()]))

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
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


def test_real_runtime_uses_one_single_request_no_retry_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport(
        200,
        {
            "success": True,
            "data": [
                {
                    "platform": "STEAM",
                    "platformItemId": "private-steam-id",
                    "sellPrice": "9999",
                    "sellCount": 2,
                    "biddingPrice": "99999",
                    "biddingCount": 1,
                    "updateTime": 123,
                },
                {
                    "platform": "BUFF",
                    "platformItemId": "private-buff-id",
                    "sellPrice": "12.3400",
                    "sellCount": 3,
                    "biddingPrice": "999999",
                    "biddingCount": 4,
                    "updateTime": 456,
                },
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
    assert list(request.url.params.multi_items()) == [("marketHashName", ITEM)]
    assert len(captured_configs) == 1
    assert captured_configs[0].max_retries == 0
    assert captured_configs[0].dry_run is False
    assert transport.closed is True
    assert "price_cny: 12.3400" in output
    assert output[-1] == "SteamDT requests sent: 1"


@pytest.mark.parametrize(
    ("status_code", "payload", "reason"),
    [
        (500, {"success": False}, "price_provider_failed"),
        (429, {"success": False}, "price_provider_failed"),
        (200, ["raw"], "price_provider_failed"),
        (200, {"success": True, "data": []}, "buff_record_missing"),
    ],
)
def test_real_runtime_failures_make_one_attempt_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: object,
    reason: str,
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
    assert f"reason: {reason}" in output
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

    failure = KeyboardInterrupt()

    def failing_client(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", failing_client)

    try:
        asyncio.run(
            smoke._create_http_smoke_runtime(
                "https://example.invalid",
                "secret",
            )
        )
    except KeyboardInterrupt as caught:
        assert caught is failure
    else:
        raise AssertionError("construction failure should propagate")

    assert http_client.close_calls == 1


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_entrypoints_are_zero_network_safe(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env[smoke.API_KEY_ENV] = "entrypoint-secret"
    env[smoke.MARKET_HASH_NAME_ENV] = ITEM
    env[smoke.BASE_URL_ENV] = "https://must-not-connect.invalid"
    env["REDIS_URL"] = "redis://must-not-connect.invalid/15"
    command = (
        [sys.executable, "scripts/run_live_steamdt_buff_price_provider_smoke.py"]
        if entrypoint == "direct"
        else [sys.executable, "-m", "scripts.run_live_steamdt_buff_price_provider_smoke"]
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
    assert "live_smoke_executed: no" in result.stdout
    assert "reason: opt_in_disabled" in result.stdout
    assert "SteamDT requests sent: 0" in result.stdout
    assert "entrypoint-secret" not in result.stdout
    assert ITEM not in result.stdout
    assert "must-not-connect.invalid" not in result.stdout


def test_script_has_only_the_provider_smoke_architecture() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "scripts" / "run_live_steamdt_buff_price_provider_smoke.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    called_attributes: list[str] = []
    called_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called_attributes.append(node.func.attr.casefold())
            elif isinstance(node.func, ast.Name):
                called_names.append(node.func.id.casefold())

    forbidden_import_fragments = {
        "redis",
        "cache",
        "valuation",
        "recipe",
        "steamapis",
        "ev_engine",
        "risk",
        "pipeline",
        "scheduler",
        "fastapi",
        "discord",
        "database",
        "app.config",
        "dotenv",
    }
    forbidden_calls = {
        "get_prices",
        "get_steamdt_market_data",
        "select_buff_output_price",
        "get_price_batch",
        "get_base_item_info",
        "get_avg_price",
        "get_kline",
        "get_wear_info",
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_import_fragments
    )
    assert not forbidden_calls.intersection(called_attributes + called_names)
    assert called_attributes.count("get_price") == 1
    assert source.count("max_retries=0") == 1
    while_nodes = (ast.AsyncFor, ast.While)
    assert not any(isinstance(node, while_nodes) for node in ast.walk(tree))
    for_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.For)]
    assert len(for_nodes) == 1
    assert isinstance(for_nodes[0].iter, ast.Name)
    assert for_nodes[0].iter.id == "lines"
    for forbidden in (
        "purchase",
        "auto_buy",
        "cookie",
        "captcha",
        "browser",
        "login",
    ):
        assert forbidden not in source.casefold()


def test_protected_authorities_do_not_reverse_import_smoke() -> None:
    project_root = Path(__file__).resolve().parents[1]
    smoke_name = "run_live_steamdt_buff_price_provider_smoke"
    protected = [
        project_root / "app" / "clients" / "steamdt_client.py",
        project_root / "app" / "services" / "steamdt_market_data.py",
        project_root / "app" / "services" / "steamdt_buff_price_policy.py",
        project_root / "app" / "services" / "steamdt_buff_price_provider.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "live_recipe_valuation.py",
    ]

    for path in protected:
        assert smoke_name not in path.read_text(encoding="utf-8")


def test_env_example_declares_only_one_dedicated_disabled_gate() -> None:
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8"
    )

    assert env_example.count("STEAMDT_RUN_BUFF_PROVIDER_SMOKE=false") == 1
