import ast
import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from scripts import steamdt_price_snapshot_smoke as smoke

BASE_TIME = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
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


class FakeCandidateClient:
    def __init__(
        self,
        candidates: list[SteamDTPlatformPrice],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.candidates = candidates
        self.error = error
        self.calls: list[str] = []

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        self.calls.append(market_hash_name)
        if self.error is not None:
            raise self.error
        return self.candidates


class FakeRuntime:
    def __init__(
        self,
        client: FakeCandidateClient,
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


def _candidate(
    platform: str = "buff",
    *,
    price: str = "12.3400",
    sell_count: int = 2,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id="id-1",
        sell_price_cny=Decimal(price),
        sell_count=sell_count,
        bidding_price_cny=Decimal("11.11"),
        bidding_count=1,
        update_time="opaque",
        raw=raw,
    )


def _enabled_environment(api_key: str = "dummy-secret") -> dict[str, str]:
    return {
        smoke.RUN_GATE_ENV: "true",
        "STEAMDT_DRY_RUN": "true",
        "STEAMDT_API_KEY": api_key,
        "STEAMDT_SMOKE_MARKET_HASH_NAME": f" {ITEM} ",
        "STEAMDT_BASE_URL": "https://example.invalid",
    }


def test_default_disabled_exits_before_secret_or_client_access() -> None:
    environ = GuardedEnvironment(
        {},
        {
            "STEAMDT_API_KEY",
            "STEAMDT_SMOKE_MARKET_HASH_NAME",
            "STEAMDT_BASE_URL",
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
    assert output[-1] == "SteamDT requests sent: 0"
    assert smoke.RUN_GATE_ENV in output[0]


@pytest.mark.parametrize("gate", ["false", "1", "yes", " true-ish "])
def test_only_explicit_true_enables_smoke(gate: str) -> None:
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


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({smoke.RUN_GATE_ENV: "true"}, "STEAMDT_API_KEY is missing"),
        (
            {smoke.RUN_GATE_ENV: "true", "STEAMDT_API_KEY": "dummy-secret"},
            "STEAMDT_SMOKE_MARKET_HASH_NAME is missing",
        ),
    ],
)
def test_enabled_guards_do_not_create_runtime(
    environ: dict[str, str],
    expected: str,
) -> None:
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
    assert expected in output[0]
    assert output[-1] == "SteamDT requests sent: 0"


def test_enabled_fake_runtime_runs_complete_source_refresh_cache_resolve_flow() -> None:
    secret = "dummy-secret"
    raw = {"Authorization": f"Bearer {secret}", "full_payload": "must-not-print"}
    client = FakeCandidateClient(
        [
            _candidate("cheap-empty", price="10.00", sell_count=0, raw=raw),
            _candidate("buff", price="12.3400", sell_count=3, raw=raw),
        ]
    )
    runtime = FakeRuntime(client)
    output: list[str] = []
    factory_calls: list[tuple[str, str]] = []

    async def factory(base_url: str, api_key: str) -> FakeRuntime:
        factory_calls.append((base_url, api_key))
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(secret),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    rendered = "\n".join(output)
    assert result == 0
    assert factory_calls == [("https://example.invalid", secret)]
    assert client.calls == [ITEM]
    assert runtime.close_calls == 1
    assert f'item: "{ITEM}"' in rendered
    assert "candidate count: 2" in rendered
    assert "cache write result: created" in rendered
    assert "cache state: fresh" in rendered
    assert 'selected platform: "buff"' in rendered
    assert "selected price: 12.3400" in rendered
    assert "needs_refresh: False" in rendered
    assert "resolution status: selected" in rendered
    assert output[-1] == "SteamDT requests sent: 1"
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "full_payload" not in rendered


def test_smoke_escapes_control_characters_in_external_summary_fields() -> None:
    item = "Item\nInjected: true"
    client = FakeCandidateClient([_candidate("platform\nInjected: true")])
    runtime = FakeRuntime(client)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    environ = _enabled_environment()
    environ["STEAMDT_SMOKE_MARKET_HASH_NAME"] = item
    result = asyncio.run(
        smoke.async_main(
            environ,
            printer=output.append,
            runtime_factory=factory,
        )
    )

    assert result == 0
    rendered = "\n".join(output)
    assert 'item: "Item\\nInjected: true"' in rendered
    assert 'selected platform: "platform\\nInjected: true"' in rendered
    assert "\nInjected: true\n" not in rendered


def test_empty_candidates_report_no_write_and_cache_miss() -> None:
    client = FakeCandidateClient([])
    runtime = FakeRuntime(client)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    rendered = "\n".join(output)
    assert result == 0
    assert "candidate count: 0" in rendered
    assert "cache write result: None" in rendered
    assert "cache state: None" in rendered
    assert "selected platform: None" in rendered
    assert "refresh status: no_candidates" in rendered
    assert "resolution status: miss" in rendered
    assert runtime.close_calls == 1


@pytest.mark.parametrize("request_count", [0, 2])
def test_enabled_smoke_rejects_request_count_other_than_one(
    request_count: int,
) -> None:
    runtime = FakeRuntime(FakeCandidateClient([_candidate()]), request_count=request_count)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    assert result == 1
    assert "RuntimeError" in output[-2]
    assert output[-1] == f"SteamDT requests sent: {request_count}"
    assert runtime.close_calls == 1


@pytest.mark.parametrize("request_count", [True, 1.0, -1])
def test_enabled_smoke_rejects_invalid_request_count_contract(
    request_count: object,
) -> None:
    runtime = FakeRuntime(FakeCandidateClient([_candidate()]), request_count=request_count)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    assert result == 1
    assert "TypeError" in output[-2]
    assert output[-1] == "SteamDT requests sent: unavailable"
    assert runtime.close_calls == 1


class RaisingRequestCountRuntime(FakeRuntime):
    @property
    def request_count(self) -> int:
        raise RuntimeError("counter unavailable")


def test_raising_request_counter_is_reported_without_masking_or_leaking() -> None:
    runtime = RaisingRequestCountRuntime(FakeCandidateClient([_candidate()]))
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> RaisingRequestCountRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    assert result == 1
    assert "RuntimeError" in output[-2]
    assert output[-1] == "SteamDT requests sent: unavailable"
    assert runtime.close_calls == 1


def test_source_failure_is_redacted_and_runtime_is_closed() -> None:
    secret = "dummy-secret"
    client = FakeCandidateClient(
        [],
        error=RuntimeError(f"Authorization: Bearer {secret}; full raw payload"),
    )
    runtime = FakeRuntime(client)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(secret),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    rendered = "\n".join(output)
    assert result == 1
    assert "RuntimeError" in rendered
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "full raw payload" not in rendered
    assert runtime.close_calls == 1
    assert output[-1] == "SteamDT requests sent: 1"


def test_cancellation_propagates_after_runtime_is_closed() -> None:
    client = FakeCandidateClient([], error=asyncio.CancelledError())
    runtime = FakeRuntime(client)

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            smoke.async_main(
                _enabled_environment(),
                runtime_factory=factory,
            )
        )

    assert runtime.close_calls == 1


def test_printer_failure_happens_after_runtime_is_closed() -> None:
    runtime = FakeRuntime(FakeCandidateClient([_candidate()]))

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


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {
                        "platform": "buff",
                        "sellPrice": "12.34",
                        "sellCount": 2,
                    }
                ],
            },
        )

    async def aclose(self) -> None:
        self.closed = True


def test_real_httpx_request_hook_counts_one_attempt_and_runtime_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = CountingTransport()
    original_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", client_factory)
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
        )
    )

    assert result == 0
    assert len(transport.requests) == 1
    assert transport.requests[0].url.path == "/open/cs2/v1/price/single"
    assert transport.closed is True
    assert output[-1] == "SteamDT requests sent: 1"


class StaticResponseTransport(httpx.AsyncBaseTransport):
    def __init__(self, *, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.payload)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_error"),
    [
        (500, {"success": False}, "SteamDTHttpStatusError"),
        (429, {"success": False}, "SteamDTRateLimitError"),
        (200, ["not-an-object"], "SteamDTResponseParseError"),
    ],
)
def test_real_runtime_failure_attempts_once_reports_count_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: object,
    expected_error: str,
) -> None:
    transport = StaticResponseTransport(status_code=status_code, payload=payload)
    original_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", client_factory)
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
        )
    )

    assert result == 1
    assert len(transport.requests) == 1
    assert transport.closed is True
    assert expected_error in output[-2]
    assert output[-1] == "SteamDT requests sent: 1"


def test_external_summary_fields_redact_api_key_and_authorization() -> None:
    secret = "summary-secret"
    item = f"Item {secret}"
    client = FakeCandidateClient(
        [_candidate(f"Authorization: Bearer {secret}")]
    )
    runtime = FakeRuntime(client)
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    environ = _enabled_environment(secret)
    environ["STEAMDT_SMOKE_MARKET_HASH_NAME"] = item
    result = asyncio.run(
        smoke.async_main(
            environ,
            printer=output.append,
            runtime_factory=factory,
        )
    )

    rendered = "\n".join(output)
    assert result == 0
    assert secret not in rendered
    assert "Authorization:" not in rendered
    assert "[REDACTED]" in rendered


def test_unsafe_dynamic_error_type_name_uses_fixed_fallback() -> None:
    unsafe_error_type = type("Bad\nInjected\x1b", (RuntimeError,), {})
    runtime = FakeRuntime(
        FakeCandidateClient([], error=unsafe_error_type("secret"))
    )
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    assert result == 1
    assert output[-2] == "SteamDT price snapshot smoke failed: InternalError"
    assert "Injected" not in "\n".join(output)


class TrackedHttpClient:
    def __init__(self, *, close_error: BaseException | None = None) -> None:
        self.close_error = close_error
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def test_default_runtime_closes_httpx_client_when_wrapper_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client = TrackedHttpClient()

    def http_factory(**_kwargs):
        return http_client

    class ConstructionFailure(RuntimeError):
        pass

    def failing_client(*_args, **_kwargs):
        raise ConstructionFailure("failed")

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", failing_client)

    with pytest.raises(ConstructionFailure):
        asyncio.run(smoke._create_http_smoke_runtime("https://example.invalid", "key"))

    assert http_client.close_calls == 1


def test_close_failure_returns_failure_without_exposing_message() -> None:
    secret = "dummy-secret"
    runtime = FakeRuntime(
        FakeCandidateClient([_candidate()]),
        close_error=RuntimeError(f"close leaked {secret}"),
    )
    output: list[str] = []

    async def factory(_base_url: str, _api_key: str) -> FakeRuntime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(secret),
            printer=output.append,
            runtime_factory=factory,
        )
    )

    rendered = "\n".join(output)
    assert result == 1
    assert "close failed: RuntimeError" in rendered
    assert secret not in rendered
    assert runtime.close_calls == 1


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_direct_and_module_entrypoints_are_safe(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env["STEAMDT_API_KEY"] = "entrypoint-secret"
    env["STEAMDT_BASE_URL"] = "https://must-not-connect.invalid"
    env["REDIS_URL"] = "redis://must-not-connect.invalid/15"

    if entrypoint == "direct":
        command = [sys.executable, "scripts/steamdt_price_snapshot_smoke.py"]
    else:
        command = [sys.executable, "-m", "scripts.steamdt_price_snapshot_smoke"]

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
    assert "ModuleNotFoundError" not in combined
    assert smoke.RUN_GATE_ENV in combined
    assert "SteamDT requests sent: 0" in combined
    assert "entrypoint-secret" not in combined
    assert "must-not-connect.invalid" not in combined


def test_smoke_module_has_no_redis_factory_pipeline_scheduler_or_fastapi_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "steamdt_price_snapshot_smoke.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
    forbidden = {
        "redis",
        "price_cache_factory",
        "steamdt_rate_limiter_factory",
        "price_provider",
        "pipeline",
        "scheduler",
        "fastapi",
        "alert",
        "app.config",
    }
    assert not any(
        fragment.casefold() in imported
        for imported in imports
        for fragment in forbidden
    )
    assert "asyncio.create_task" not in module_path.read_text(encoding="utf-8")
