from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_live_buff_listing_provider_smoke as smoke
from scripts.buff_listing_smoke_utils import BuffListingSmokeRequestState

GOODS_ID = "synthetic-goods"
VALID_PAYLOAD = (
    b'{"code":"OK","data":{"items":[{"id":"listing","price":"1.25",'
    b'"asset_info":{"assetid":"asset","paintwear":"0.1"}}]}}'
)


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


class Client:
    def __init__(self, payload: bytes = VALID_PAYLOAD, error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        self.calls.append(goods_id)
        if self.error is not None:
            raise self.error
        return self.payload


class Runtime:
    def __init__(
        self,
        client: Client,
        *,
        state: BuffListingSmokeRequestState | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.client = client
        self.request_state = state or BuffListingSmokeRequestState(
            attempted=1,
            dispatched=1,
            budget_exceeded=False,
        )
        self.close_error = close_error
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class RaisingStateRuntime(Runtime):
    @property
    def request_state(self):
        raise RuntimeError("state unavailable")

    @request_state.setter
    def request_state(self, _value: object) -> None:
        pass


def _run(runtime: Runtime) -> tuple[int, list[str]]:
    output: list[str] = []

    async def factory(_goods_id: str) -> Runtime:
        return runtime

    result = asyncio.run(
        smoke.async_main(
            {smoke.RUN_GATE_ENV: "true", smoke.GOODS_ID_ENV: GOODS_ID},
            printer=output.append,
            runtime_factory=factory,
        )
    )
    return result, output


def test_gate_off_is_zero_network() -> None:
    output: list[str] = []
    result = asyncio.run(smoke.async_main({}, printer=output.append))
    assert result == 0
    assert output == [
        "live_smoke_executed: no",
        "reason: opt_in_disabled",
        "BUFF requests sent: 0",
    ]


@pytest.mark.parametrize("goods", [None, "", "   "])
def test_missing_goods_id_is_zero_network(goods: str | None) -> None:
    env = {smoke.RUN_GATE_ENV: "true"}
    if goods is not None:
        env[smoke.GOODS_ID_ENV] = goods
    output: list[str] = []
    assert asyncio.run(smoke.async_main(env, printer=output.append)) == 1
    assert "reason: goods_id_missing" in output
    assert output[-1] == "BUFF requests sent: 0"


def test_success_reuses_provider_and_is_redacted() -> None:
    runtime = Runtime(Client())
    result, output = _run(runtime)
    assert result == 0
    assert runtime.client.calls == [GOODS_ID]
    assert runtime.close_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: success",
        "listing_count: 1",
        "first_listing_id_present: yes",
        "first_listing_price_valid: yes",
        "first_listing_paintwear_valid: yes",
        "BUFF requests sent: 1",
    ]
    assert GOODS_ID not in "\n".join(output)
    rendered_without_labels = "\n".join(output).replace(
        "listing_count", ""
    ).replace("first_listing", "")
    assert "listing" not in rendered_without_labels


def test_empty_page_fails_safely() -> None:
    runtime = Runtime(Client(b'{"code":"OK","data":{"items":[]}}'))
    result, output = _run(runtime)
    assert result == 1
    assert "reason: no_items" in output


def test_provider_failure_is_redacted() -> None:
    runtime = Runtime(Client(error=RuntimeError("Cookie secret URL")))
    result, output = _run(runtime)
    assert result == 1
    assert "reason: provider_failed" in output
    rendered = "\n".join(output)
    assert "Cookie secret" not in rendered
    assert "RuntimeError" not in rendered


def test_invalid_request_state_fails_closed() -> None:
    runtime = Runtime(
        Client(),
        state=BuffListingSmokeRequestState(
            attempted=2,
            dispatched=1,
            budget_exceeded=True,
        ),
    )
    result, output = _run(runtime)
    assert result == 1
    assert "reason: request_count_invalid" in output


def test_unreadable_request_state_overrides_provider_failure() -> None:
    runtime = RaisingStateRuntime(Client(error=RuntimeError("ordinary")))
    result, output = _run(runtime)
    assert result == 1
    assert "reason: request_count_invalid" in output


def test_close_failure_replaces_success() -> None:
    runtime = Runtime(Client(), close_error=RuntimeError("secret"))
    result, output = _run(runtime)
    assert result == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: close_failed",
        "BUFF requests sent: 1",
    ]


@pytest.mark.parametrize(
    "error",
    [MemoryError(), asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(3)],
)
def test_process_control_propagates_after_cleanup(error: BaseException) -> None:
    runtime = Runtime(Client(error=error))
    try:
        _run(runtime)
    except BaseException as caught:
        assert caught is error
    else:
        raise AssertionError("process control must propagate")
    assert runtime.close_calls == 1


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_entrypoints_are_offline(entrypoint: str) -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env[smoke.GOODS_ID_ENV] = "private"
    command = (
        [sys.executable, "scripts/run_live_buff_listing_provider_smoke.py"]
        if entrypoint == "direct"
        else [sys.executable, "-m", "scripts.run_live_buff_listing_provider_smoke"]
    )
    result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode == 0
    assert "reason: opt_in_disabled" in result.stdout
    assert "private" not in result.stdout


def test_source_has_no_forbidden_behavior() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_live_buff_listing_provider_smoke.py"
    ).read_text(encoding="utf-8").casefold()
    for marker in (
        "app.clients.steamapis",
        "app.clients.steamdt",
        "cookie=",
        "login(",
        "purchase(",
        "retry",
        "backoff",
        "page_size",
        "create_task",
        "gather(",
    ):
        assert marker not in source
