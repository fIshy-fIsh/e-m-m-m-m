from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

import app.services.live_recipe_valuation as live_valuation_module
from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.live_recipe_valuation import (
    LiveRecipeValuationRejection,
    LiveRecipeValuationRejectionReason,
    LiveRecipeValuationResult,
)
from app.services.price_provider import PriceQuote
from app.services.steamdt_buff_live_recipe_fixture import (
    STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
    SteamDTBuffLiveRecipeFixture,
    build_verified_steamdt_buff_live_recipe_fixture,
)
from app.services.tradeup_engine import TradeupResult
from scripts import run_live_steamdt_buff_live_recipe_valuation_smoke as smoke

PRICE = Decimal("812.3456700")
SECRET = "a5-dummy-secret"
BASE_URL = "https://example.invalid"


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
        records: list[SteamDTPlatformPrice],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.records = records
        self.error = error
        self.calls: list[str] = []

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        self.calls.append(market_hash_name)
        if self.error is not None:
            raise self.error
        return self.records


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


class DirectControlFlow(BaseException):
    pass


def _record(
    platform: str = "BUFF",
    *,
    sell_price: Decimal | None = PRICE,
    bidding_price: Decimal | None = Decimal("999999.99"),
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id="opaque-platform-id",
        sell_price_cny=sell_price,
        sell_count=3,
        bidding_price_cny=bidding_price,
        bidding_count=4,
        update_time=456,
        raw=raw,
    )


def _tampered_sell(value: Decimal) -> SteamDTPlatformPrice:
    record = _record()
    object.__setattr__(record, "sell_price_cny", value)
    return record


def _enabled_environment(secret: str = SECRET) -> dict[str, str]:
    return {
        smoke.RUN_GATE_ENV: "true",
        smoke.API_KEY_ENV: secret,
        smoke.BASE_URL_ENV: BASE_URL,
    }


def _success_records() -> list[SteamDTPlatformPrice]:
    raw = {
        "Authorization": "Bearer raw-secret",
        "raw_response": "private-response",
        "request_url": "https://private.invalid/item",
    }
    return [
        _record(
            "STEAM",
            sell_price=Decimal("9999.99"),
            bidding_price=Decimal("99999.99"),
            raw=raw,
        ),
        _record(
            "YOUPIN",
            sell_price=Decimal("8888.88"),
            bidding_price=Decimal("88888.88"),
            raw=raw,
        ),
        _record(raw=raw),
    ]


def _run_with_runtime(
    runtime: FakeRuntime,
    *,
    environ: Mapping[str, str] | None = None,
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


def _assert_process_control_identity(
    runtime: FakeRuntime,
    error: BaseException,
) -> None:
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


def _set_recipe_count(fixture: SteamDTBuffLiveRecipeFixture, count: int) -> None:
    live_recipe = fixture.construction_result.recipes[0]
    object.__setattr__(
        fixture.construction_result,
        "recipes",
        tuple(live_recipe for _index in range(count)),
    )


def _set_input_count(fixture: SteamDTBuffLiveRecipeFixture, count: int) -> None:
    recipe = fixture.construction_result.recipes[0].recipe
    original = recipe.input_items
    repeated = tuple(original[index % len(original)] for index in range(count))
    object.__setattr__(recipe, "input_items", repeated)


def _set_outputs(
    fixture: SteamDTBuffLiveRecipeFixture,
    output_names: tuple[str, ...],
) -> None:
    recipe = fixture.construction_result.recipes[0].recipe
    original = recipe.tradeup_results[0]
    results = tuple(
        replace(original, output_market_hash_name=name) for name in output_names
    )
    object.__setattr__(recipe, "tradeup_results", results)


def _rejection_result(
    reason: LiveRecipeValuationRejectionReason,
) -> LiveRecipeValuationResult:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    selected_ids = fixture.construction_result.recipes[0].selected_source_offer_ids
    return LiveRecipeValuationResult(
        opportunities=(),
        rejected=(
            LiveRecipeValuationRejection(
                selected_source_offer_ids=selected_ids,
                reason_code=reason,
            ),
        ),
    )


def test_public_environment_contract_is_exact_and_has_no_name_env() -> None:
    assert smoke.RUN_GATE_ENV == (
        "STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE"
    )
    assert smoke.API_KEY_ENV == "STEAMDT_API_KEY"
    assert smoke.BASE_URL_ENV == "STEAMDT_BASE_URL"
    assert smoke.DEFAULT_BASE_URL == "https://open.steamdt.com"
    assert not hasattr(smoke, "MARKET_HASH_NAME_ENV")


def test_default_disabled_stops_before_key_base_fixture_or_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environ = GuardedEnvironment(
        {},
        {
            smoke.API_KEY_ENV,
            smoke.BASE_URL_ENV,
            "STEAMDT_SMOKE_MARKET_HASH_NAME",
        },
    )
    output: list[str] = []

    def forbidden_builder() -> None:
        raise AssertionError("fixture must not be built")

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        forbidden_builder,
    )
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
def test_normalized_true_variants_enable_without_market_name_env(gate: str) -> None:
    runtime = FakeRuntime(FakeClient(_success_records()))
    environ = GuardedEnvironment(
        {
            smoke.RUN_GATE_ENV: gate,
            smoke.API_KEY_ENV: SECRET,
            smoke.BASE_URL_ENV: BASE_URL,
        },
        {"STEAMDT_SMOKE_MARKET_HASH_NAME"},
    )

    result, output, _factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert "result: success" in output


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_stops_before_base_fixture_or_runtime(
    key: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {smoke.RUN_GATE_ENV: "true"}
    if key is not None:
        values[smoke.API_KEY_ENV] = key
    environ = GuardedEnvironment(
        values,
        {smoke.BASE_URL_ENV, "STEAMDT_SMOKE_MARKET_HASH_NAME"},
    )
    output: list[str] = []

    def forbidden_builder() -> None:
        raise AssertionError("fixture must not be built")

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        forbidden_builder,
    )
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


def test_verified_builder_is_called_once_without_arguments_and_key_is_trimmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_builder = build_verified_steamdt_buff_live_recipe_fixture
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def builder(*args: object, **kwargs: object) -> SteamDTBuffLiveRecipeFixture:
        calls.append((args, kwargs))
        return real_builder()

    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        builder,
    )
    runtime = FakeRuntime(FakeClient(_success_records()))
    environ = _enabled_environment()
    environ[smoke.API_KEY_ENV] = f"  {SECRET}  "

    result, _output, factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert calls == [((), {})]
    assert factory_calls == [(BASE_URL, SECRET)]
    assert runtime.client.calls == [
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    ]


def test_default_base_url_is_used_only_after_fixture_guards() -> None:
    runtime = FakeRuntime(FakeClient(_success_records()))
    environ = _enabled_environment()
    del environ[smoke.BASE_URL_ENV]

    result, _output, factory_calls = _run_with_runtime(runtime, environ=environ)

    assert result == 0
    assert factory_calls == [(smoke.DEFAULT_BASE_URL, SECRET)]


@pytest.mark.parametrize(
    "builder_value",
    [None, object(), "fixture"],
)
def test_wrong_fixture_type_fails_before_runtime(
    builder_value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: builder_value,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: no",
        "result: failed",
        "reason: fixture_invalid",
        "SteamDT requests sent: 0",
    ]


def test_ordinary_fixture_builder_failure_is_fixed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "fixture-leaked-secret"

    def failing_builder() -> None:
        raise RuntimeError(f"Authorization: Bearer {secret}")

    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        failing_builder,
    )
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(_enabled_environment(secret), printer=output.append)
    )

    assert result == 1
    assert "reason: fixture_invalid" in output
    rendered = "\n".join(output)
    assert secret not in rendered
    assert "RuntimeError" not in rendered
    assert "Authorization" not in rendered


@pytest.mark.parametrize("count", [0, 2])
def test_recipe_count_invalid_stops_before_runtime(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    _set_recipe_count(fixture, count)
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: recipe_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: 0"


@pytest.mark.parametrize("count", [9, 11])
def test_input_count_invalid_stops_before_runtime(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    _set_input_count(fixture, count)
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: input_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: 0"


@pytest.mark.parametrize(
    "names",
    [(), ("Output One", "Output Two")],
)
def test_output_count_invalid_stops_before_runtime(
    names: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    _set_outputs(fixture, names)
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: output_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: 0"


def test_malformed_input_item_is_fixture_invalid_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    recipe = fixture.construction_result.recipes[0].recipe
    object.__setattr__(
        recipe,
        "input_items",
        (object(), *recipe.input_items[1:]),
    )
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: fixture_invalid" in output
    assert output[-1] == "SteamDT requests sent: 0"


def test_wrong_single_output_identity_is_fixture_invalid_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    _set_outputs(fixture, ("Wrong Output (Factory New)",))
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    output: list[str] = []

    async def forbidden_factory(_base_url: str, _api_key: str):
        raise AssertionError("runtime must not be created")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(),
            printer=output.append,
            runtime_factory=forbidden_factory,
        )
    )

    assert result == 1
    assert "reason: fixture_invalid" in output
    assert output[-1] == "SteamDT requests sent: 0"


def test_runtime_failure_is_fixed_and_zero_request_and_redacted() -> None:
    secret = "runtime-secret"
    output: list[str] = []

    async def failing_factory(_base_url: str, _api_key: str):
        raise RuntimeError(f"Authorization: Bearer {secret}; https://private.invalid")

    result = asyncio.run(
        smoke.async_main(
            _enabled_environment(secret),
            printer=output.append,
            runtime_factory=failing_factory,
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: runtime_failed",
        "SteamDT requests sent: 0",
    ]
    rendered = "\n".join(output)
    assert secret not in rendered
    assert "RuntimeError" not in rendered
    assert "private.invalid" not in rendered


def test_complete_real_chain_uses_buff_sell_runs_metrics_and_risk_and_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    original_metrics = live_valuation_module.calculate_opportunity_metrics
    original_risk = live_valuation_module.evaluate_opportunity
    metric_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    risk_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    seen_sources: list[str] = []
    captured_results: list[LiveRecipeValuationResult] = []
    original_validator = live_valuation_module._validate_aligned_quote
    original_composition = smoke.value_live_recipes_with_steamdt_buff_prices

    def capture_metrics(*args: object, **kwargs: object):
        metric_calls.append((args, kwargs))
        return original_metrics(*args, **kwargs)  # type: ignore[arg-type]

    def capture_risk(*args: object, **kwargs: object):
        risk_calls.append((args, kwargs))
        return original_risk(*args, **kwargs)  # type: ignore[arg-type]

    def capture_source(
        value: object,
        expected_name: str,
        result: TradeupResult,
    ) -> None:
        if type(value) is PriceQuote:
            seen_sources.append(value.source)
        original_validator(value, expected_name, result)

    async def capture_composition(**kwargs: object) -> LiveRecipeValuationResult:
        result = await original_composition(**kwargs)  # type: ignore[arg-type]
        captured_results.append(result)
        return result

    monkeypatch.setattr(
        live_valuation_module,
        "calculate_opportunity_metrics",
        capture_metrics,
    )
    monkeypatch.setattr(live_valuation_module, "evaluate_opportunity", capture_risk)
    monkeypatch.setattr(
        live_valuation_module,
        "_validate_aligned_quote",
        capture_source,
    )
    monkeypatch.setattr(
        smoke,
        "value_live_recipes_with_steamdt_buff_prices",
        capture_composition,
    )
    runtime = FakeRuntime(FakeClient(_success_records()))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 0
    assert runtime.client.calls == [
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    ]
    assert runtime.close_calls == 1
    assert seen_sources == ["steamdt:buff"]
    assert len(metric_calls) == 1
    assert len(risk_calls) == 1
    assert risk_calls[0][1]["paint_seeds"] == list(
        fixture.construction_result.recipes[0].recipe.paint_seeds
    )
    assert len(captured_results) == 1
    valuation = captured_results[0]
    assert len(valuation.opportunities) == 1
    assert valuation.rejected == ()
    opportunity = valuation.opportunities[0]
    assert opportunity.valued_tradeup_results[0].estimated_price_cny == PRICE
    assert opportunity.recipe.tradeup_results[0].estimated_price_cny == 0
    assert type(opportunity.metrics.roi) is Decimal
    assert opportunity.risk_decision.passed is True
    assert output == [
        "live_smoke_executed: yes",
        "result: success",
        "construction_source: deterministic_versioned_fixture",
        "recipe_count: 1",
        "input_count: 10",
        "distinct_output_count: 1",
        "valuation_opportunities: 1",
        "valuation_rejections: 0",
        "price_source_path: steamdt:buff",
        "ev_evaluated: yes",
        "roi_evaluated: yes",
        "risk_evaluated: yes",
        "risk_passed: yes",
        "SteamDT requests sent: 1",
    ]

    rendered = "\n".join(output)
    forbidden_values = [
        str(PRICE),
        str(opportunity.metrics.expected_revenue_cny),
        str(opportunity.metrics.expected_profit_cny),
        str(opportunity.metrics.roi),
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
        SECRET,
        BASE_URL,
        "Authorization",
        "raw-secret",
        "private-response",
        "private.invalid",
        "opaque-platform-id",
        "999999.99",
        "456",
    ]
    forbidden_values.extend(opportunity.selected_source_offer_ids)
    forbidden_values.extend(str(seed) for seed in opportunity.recipe.paint_seeds)
    for forbidden in forbidden_values:
        assert forbidden not in rendered


def test_stricter_test_only_risk_config_can_fail_and_remain_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_verified_steamdt_buff_live_recipe_fixture()
    object.__setattr__(
        fixture,
        "risk_config",
        replace(fixture.risk_config, min_roi=Decimal("99")),
    )
    monkeypatch.setattr(
        smoke,
        "build_verified_steamdt_buff_live_recipe_fixture",
        lambda: fixture,
    )
    runtime = FakeRuntime(FakeClient(_success_records()))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 0
    assert "result: success" in output
    assert "risk_passed: no" in output
    assert output[-1] == "SteamDT requests sent: 1"


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_record("STEAM", sell_price=Decimal("9999"))],
        [_record("buff"), _record("BUFF163")],
        [_record(), _record()],
        [_record(sell_price=None)],
        [_record(sell_price=Decimal("0"))],
        [_tampered_sell(Decimal("-1"))],
        [_tampered_sell(Decimal("NaN"))],
        [_tampered_sell(Decimal("Infinity"))],
    ],
    ids=[
        "empty",
        "other-platform",
        "wrong-case",
        "duplicate-buff",
        "missing-sell-high-bid",
        "zero-sell-high-bid",
        "negative-sell",
        "nan-sell",
        "infinite-sell",
    ],
)
def test_invalid_buff_price_is_safe_provider_error_without_fallback(
    records: list[SteamDTPlatformPrice],
) -> None:
    runtime = FakeRuntime(FakeClient(records))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert runtime.client.calls == [
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    ]
    assert runtime.close_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: price_provider_error",
        "SteamDT requests sent: 1",
    ]


def test_incomplete_price_rejects_before_metrics_or_risk_and_never_uses_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metrics and risk must not run")

    monkeypatch.setattr(
        live_valuation_module,
        "calculate_opportunity_metrics",
        forbidden,
    )
    monkeypatch.setattr(live_valuation_module, "evaluate_opportunity", forbidden)
    runtime = FakeRuntime(FakeClient([_record("STEAM", sell_price=Decimal("9999"))]))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: price_provider_error" in output
    assert "result: success" not in output


def test_ordinary_provider_failure_is_fixed_redacted_and_closed() -> None:
    secret = "provider-secret"
    runtime = FakeRuntime(
        FakeClient(
            [],
            error=RuntimeError(
                f"Authorization: Bearer {secret}; raw response; "
                "opaque-id; https://purchase.invalid"
            ),
        )
    )

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: price_provider_error",
        "SteamDT requests sent: 1",
    ]
    rendered = "\n".join(output)
    for forbidden in (
        secret,
        "Authorization",
        "raw response",
        "opaque-id",
        "purchase.invalid",
        "RuntimeError",
    ):
        assert forbidden not in rendered
    assert runtime.close_calls == 1


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR,
            "price_provider_error",
        ),
        (
            LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE,
            "missing_output_price",
        ),
        (
            LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT,
            "invalid_valuation_result",
        ),
    ],
)
def test_existing_rejection_reasons_map_exactly(
    reason: LiveRecipeValuationRejectionReason,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(**_kwargs: object) -> LiveRecipeValuationResult:
        return _rejection_result(reason)

    monkeypatch.setattr(
        smoke,
        "value_live_recipes_with_steamdt_buff_prices",
        reject,
    )
    runtime = FakeRuntime(FakeClient([]))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert f"reason: {expected}" in output
    assert output[-1] == "SteamDT requests sent: 1"


@pytest.mark.parametrize(
    "invalid_result",
    [None, object(), "result"],
)
def test_unexpected_valuation_result_is_failed_closed(
    invalid_result: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invalid(**_kwargs: object) -> object:
        return invalid_result

    monkeypatch.setattr(
        smoke,
        "value_live_recipes_with_steamdt_buff_prices",
        invalid,
    )
    runtime = FakeRuntime(FakeClient([]))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: valuation_result_invalid" in output


def test_ordinary_valuation_escape_is_safe_valuation_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "valuation-secret"

    async def failing(**_kwargs: object) -> None:
        raise RuntimeError(f"leaked {secret}; raw provider response")

    monkeypatch.setattr(
        smoke,
        "value_live_recipes_with_steamdt_buff_prices",
        failing,
    )
    runtime = FakeRuntime(FakeClient([]))

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: valuation_failed" in output
    rendered = "\n".join(output)
    assert secret not in rendered
    assert "RuntimeError" not in rendered
    assert "raw provider response" not in rendered


@pytest.mark.parametrize("request_count", [0, 2])
def test_success_request_count_other_than_one_fails(request_count: int) -> None:
    runtime = FakeRuntime(
        FakeClient(_success_records()),
        request_count=request_count,
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == f"SteamDT requests sent: {request_count}"
    assert "result: success" not in output


@pytest.mark.parametrize("request_count", [True, 1.0, -1])
def test_invalid_success_request_counter_is_unavailable(
    request_count: object,
) -> None:
    runtime = FakeRuntime(
        FakeClient(_success_records()),
        request_count=request_count,
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: unavailable"


def test_raising_ordinary_request_counter_is_unavailable_and_redacted() -> None:
    runtime = RaisingRequestCountRuntime(
        FakeClient(_success_records()),
        RuntimeError("counter leaked Authorization: Bearer secret"),
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: unavailable"
    rendered = "\n".join(output)
    assert "counter leaked" not in rendered
    assert "RuntimeError" not in rendered


def test_more_than_one_request_overrides_provider_failure() -> None:
    runtime = FakeRuntime(
        FakeClient([], error=RuntimeError("ordinary")),
        request_count=2,
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: request_count_invalid" in output
    assert output[-1] == "SteamDT requests sent: 2"


@pytest.mark.parametrize("request_count", [0, True])
def test_non_excess_count_retains_primary_failure(request_count: object) -> None:
    runtime = FakeRuntime(
        FakeClient([], error=RuntimeError("ordinary")),
        request_count=request_count,
    )

    result, output, _factory_calls = _run_with_runtime(runtime)

    assert result == 1
    assert "reason: price_provider_error" in output
    expected = "0" if request_count == 0 else "unavailable"
    assert output[-1] == f"SteamDT requests sent: {expected}"


def test_close_failure_replaces_success_without_partial_summary() -> None:
    secret = "close-secret"
    runtime = FakeRuntime(
        FakeClient(_success_records()),
        close_error=RuntimeError(f"close leaked {secret}"),
    )

    result, output, _factory_calls = _run_with_runtime(
        runtime,
        environ=_enabled_environment(secret),
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: close_failed",
        "SteamDT requests sent: 1",
    ]
    assert secret not in "\n".join(output)
    assert runtime.close_calls == 1


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
def test_process_control_from_valuation_propagates_after_cleanup(
    error: BaseException,
) -> None:
    runtime = FakeRuntime(FakeClient([], error=error))
    _assert_process_control_identity(runtime, error)


@pytest.mark.parametrize(
    "error",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancel"),
        KeyboardInterrupt(),
        SystemExit(4),
    ],
)
def test_request_counter_process_control_propagates_after_cleanup(
    error: BaseException,
) -> None:
    runtime = RaisingRequestCountRuntime(FakeClient(_success_records()), error)
    _assert_process_control_identity(runtime, error)


def test_printer_failure_occurs_after_runtime_cleanup() -> None:
    runtime = FakeRuntime(FakeClient(_success_records()))

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


def test_real_runtime_uses_one_single_request_zero_retry_and_closes(
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
                    "sellPrice": "9999.99",
                    "sellCount": 2,
                    "biddingPrice": "99999.99",
                    "biddingCount": 1,
                    "updateTime": 123,
                },
                {
                    "platform": "BUFF",
                    "platformItemId": "private-buff-id",
                    "sellPrice": str(PRICE),
                    "sellCount": 3,
                    "biddingPrice": "999999.99",
                    "biddingCount": 4,
                    "updateTime": 456,
                },
            ],
        },
    )
    original_async_client = httpx.AsyncClient
    original_client = smoke.SteamDTHttpClient
    captured_configs: list[object] = []

    def http_factory(*args: object, **kwargs: object):
        assert kwargs["follow_redirects"] is False
        return original_async_client(*args, transport=transport, **kwargs)

    def client_factory(config: object, *args: object, **kwargs: object):
        captured_configs.append(config)
        return original_client(config, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", client_factory)
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(_enabled_environment(), printer=output.append)
    )

    assert result == 0
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/open/cs2/v1/price/single"
    assert list(request.url.params.multi_items()) == [
        (
            "marketHashName",
            STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
        )
    ]
    assert len(captured_configs) == 1
    config = captured_configs[0]
    assert config.max_retries == 0
    assert config.dry_run is False
    assert transport.closed is True
    assert "result: success" in output
    assert str(PRICE) not in "\n".join(output)
    assert output[-1] == "SteamDT requests sent: 1"


def test_second_real_client_call_is_blocked_before_second_transport_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport(200, {"success": True, "data": []})
    original_async_client = httpx.AsyncClient

    def http_factory(*args: object, **kwargs: object):
        return original_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    runtime = asyncio.run(
        smoke._create_http_smoke_runtime(BASE_URL, SECRET)
    )
    try:
        asyncio.run(
            runtime.client.get_price_single_candidates(
                STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
            )
        )
        with pytest.raises(RuntimeError):
            asyncio.run(
                runtime.client.get_price_single_candidates(
                    STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
                )
            )
    finally:
        asyncio.run(runtime.aclose())

    assert len(transport.requests) == 1
    assert runtime.request_count == 2
    assert transport.closed is True


@pytest.mark.parametrize("status_code", [429, 500])
def test_real_runtime_http_failure_makes_one_attempt_without_retry(
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = StaticTransport(status_code, {"success": False})
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
    assert "reason: price_provider_error" in output
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

    def http_factory(**_kwargs: object) -> TrackedHttpClient:
        return http_client

    failure = KeyboardInterrupt()

    def failing_client(*_args: object, **_kwargs: object) -> None:
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


class FailingCloseHttpClient(TrackedHttpClient):
    async def aclose(self) -> None:
        self.close_calls += 1
        raise RuntimeError("ordinary close failure")


@pytest.mark.parametrize(
    "failure",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancel"),
        KeyboardInterrupt(),
        SystemExit(7),
    ],
)
def test_runtime_construction_process_control_survives_ordinary_cleanup_failure(
    failure: BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client = FailingCloseHttpClient()

    def http_factory(**_kwargs: object) -> FailingCloseHttpClient:
        return http_client

    def failing_client(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(smoke.httpx, "AsyncClient", http_factory)
    monkeypatch.setattr(smoke, "SteamDTHttpClient", failing_client)

    try:
        asyncio.run(smoke._create_http_smoke_runtime(BASE_URL, SECRET))
    except BaseException as caught:
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
    env[smoke.BASE_URL_ENV] = "https://must-not-connect.invalid"
    env["STEAMDT_SMOKE_MARKET_HASH_NAME"] = (
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    )
    env["REDIS_URL"] = "redis://must-not-connect.invalid/15"
    command = (
        [
            sys.executable,
            "scripts/run_live_steamdt_buff_live_recipe_valuation_smoke.py",
        ]
        if entrypoint == "direct"
        else [
            sys.executable,
            "-m",
            "scripts.run_live_steamdt_buff_live_recipe_valuation_smoke",
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
    assert "live_smoke_executed: no" in result.stdout
    assert "reason: opt_in_disabled" in result.stdout
    assert "SteamDT requests sent: 0" in result.stdout
    assert "entrypoint-secret" not in result.stdout
    assert STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME not in (
        result.stdout
    )
    assert "must-not-connect.invalid" not in result.stdout


def test_script_composes_only_verified_fixture_a3_and_owned_runtime() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "scripts"
        / "run_live_steamdt_buff_live_recipe_valuation_smoke.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    called_attributes: list[str] = []
    called_names: list[str] = []
    accessed_attributes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.Attribute):
            accessed_attributes.append(node.attr.casefold())
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called_attributes.append(node.func.attr.casefold())
            elif isinstance(node.func, ast.Name):
                called_names.append(node.func.id.casefold())

    forbidden_import_fragments = {
        "steamapis",
        "redis",
        "cache",
        "limiter",
        "scheduler",
        "fastapi",
        "discord",
        "database",
        "dotenv",
        "ev_service",
        "risk_filter",
        "valuation_service",
        "steamdt_buff_price_provider",
        "steamdt_buff_price_policy",
    }
    forbidden_calls = {
        "get_prices",
        "get_steamdt_market_data",
        "select_buff_output_price",
        "calculate_opportunity_metrics",
        "evaluate_opportunity",
        "get_price_batch",
        "get_base_item_info",
        "get_avg_price",
        "get_kline",
        "get_wear_info",
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
        "submit",
    }
    forbidden_economic_attributes = {
        "price_cny",
        "sell_fee_rate",
        "expected_revenue_cny",
        "expected_profit_cny",
        "roi",
        "risk_score",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_import_fragments
    )
    assert not forbidden_calls.intersection(called_attributes + called_names)
    assert not forbidden_economic_attributes.intersection(accessed_attributes)
    assert called_names.count(
        "build_verified_steamdt_buff_live_recipe_fixture"
    ) == 1
    assert called_names.count(
        "value_live_recipes_with_steamdt_buff_prices"
    ) == 1
    assert source.count("max_retries=0") == 1
    assert "STEAMDT_SMOKE_MARKET_HASH_NAME" not in source
    assert not any(
        isinstance(node, (ast.AsyncFor, ast.While)) for node in ast.walk(tree)
    )
    for forbidden in (
        "steamapis",
        "redis",
        "cache",
        "scheduler",
        "background",
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
    smoke_name = "run_live_steamdt_buff_live_recipe_valuation_smoke"
    protected = [
        project_root / "app" / "clients" / "steamdt_client.py",
        project_root / "app" / "services" / "steamdt_market_data.py",
        project_root / "app" / "services" / "steamdt_buff_price_policy.py",
        project_root / "app" / "services" / "steamdt_buff_price_provider.py",
        project_root / "app" / "services" / "steamdt_buff_live_recipe_fixture.py",
        project_root
        / "app"
        / "services"
        / "steamdt_buff_live_recipe_valuation.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "live_recipe_valuation.py",
        project_root / "app" / "services" / "ev_service.py",
        project_root / "app" / "services" / "risk_filter.py",
    ]

    for path in protected:
        assert smoke_name not in path.read_text(encoding="utf-8")


def test_env_example_declares_one_independent_disabled_gate() -> None:
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8"
    )

    assert env_example.count(
        "STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE=false"
    ) == 1
    assert env_example.count("STEAMDT_RUN_BUFF_PROVIDER_SMOKE=false") == 1
    assert env_example.count("STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE=false") == 1
