from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from app.clients.steamapis_websocket_client import (
    SteamApisWebSocketClient,
    SteamApisWebSocketConfig,
)
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
)
from app.services.steamapis_offer_pool import (
    SteamApisOfferPool,
    SteamApisOfferPoolSnapshot,
)
from app.services.steamapis_offer_session import run_steamapis_offer_session
from scripts import run_live_steamapis_offer_smoke as smoke

BASE_TIME = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
SECRET = "dummy-live-secret+/not-real"


class GuardedEnvironment(Mapping[str, str]):
    def __init__(self, values: dict[str, str], forbidden: set[str]) -> None:
        self._values = values
        self._forbidden = forbidden

    def __getitem__(self, key: str) -> str:
        if key in self._forbidden:
            raise AssertionError(f"forbidden environment read: {key}")
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default=None):
        if key in self._forbidden:
            raise AssertionError(f"forbidden environment read: {key}")
        return self._values.get(key, default)


class FakeTimeout:
    def __init__(self, *, expired: bool = False) -> None:
        self._expired = expired
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeTimeout:
        self.entered += 1
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.exited += 1

    def expired(self) -> bool:
        return self._expired


class FakePool:
    def __init__(
        self,
        observations: tuple[SteamApisListingObservation, ...] = (),
        *,
        snapshot_error: BaseException | None = None,
    ) -> None:
        self.observations = observations
        self.snapshot_error = snapshot_error
        self.snapshot_calls = 0

    def snapshot(self) -> SteamApisOfferPoolSnapshot:
        self.snapshot_calls += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return SteamApisOfferPoolSnapshot(observations=self.observations)


class ControlFlow(BaseException):
    pass


def _observation(
    token: str,
    *,
    event_type: SteamApisListingEventType = SteamApisListingEventType.ADDED,
    timestamp: datetime = BASE_TIME,
    price: str = "10.00",
) -> SteamApisListingObservation:
    purchase_link = f"https://example.invalid/manual/{token}"
    return SteamApisListingObservation(
        source_offer_id=make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            purchase_link,
        ),
        event_type=event_type,
        marketplace="Buff163",
        game="CS2",
        market_hash_name=f"Sensitive market {token}",
        purchase_link=purchase_link,
        inspect_link=f"steam://inspect/{token}",
        price_cny=Decimal(price),
        float_value=Decimal("0.1234"),
        paint_index=1,
        paint_seed=2,
        days_trade_locked=0,
        found_at=timestamp,
        message_timestamp=timestamp,
        stickers=(),
    )


def _enabled_environment(key: str = SECRET) -> dict[str, str]:
    return {
        smoke.RUN_GATE_ENV: "true",
        smoke.API_KEY_ENV: key,
    }


def _run(
    *,
    observations: tuple[SteamApisListingObservation, ...] = (),
    session_error: BaseException | None = None,
    snapshot_error: BaseException | None = None,
    seconds: int = 15,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, list[str], FakePool, FakeTimeout, list[tuple[object, object]]]:
    output: list[str] = []
    pool = FakePool(observations, snapshot_error=snapshot_error)
    timeout = FakeTimeout()
    runner_calls: list[tuple[object, object]] = []

    async def runner(*, client: object, pool: object) -> object:
        runner_calls.append((client, pool))
        if session_error is not None:
            raise session_error
        return object()

    result = asyncio.run(
        smoke.async_main(
            seconds=seconds,
            environ=_enabled_environment() if environ is None else environ,
            printer=output.append,
            client_factory=lambda _config: object(),  # type: ignore[arg-type]
            pool_factory=lambda **_kwargs: pool,  # type: ignore[arg-type]
            session_runner=runner,
            timeout_factory=lambda _seconds: timeout,
        )
    )
    return result, output, pool, timeout, runner_calls


def test_cli_duration_default_and_boundaries() -> None:
    assert smoke._parse_arguments([]) == 15
    assert smoke._parse_arguments(["--seconds", "5"]) == 5
    assert smoke._parse_arguments(["--seconds", "60"]) == 60


@pytest.mark.parametrize(
    "argv",
    [
        ["--seconds", "4"],
        ["--seconds", "61"],
        ["--seconds", "0"],
        ["--seconds", "-5"],
        ["--seconds", "5.0"],
        ["--seconds", "nan"],
        ["--seconds", "inf"],
        ["--seconds"],
        ["--unknown", "15"],
    ],
)
def test_invalid_cli_is_fixed_and_does_not_start_async_runtime(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        smoke.asyncio,
        "run",
        lambda _coroutine: pytest.fail("async runtime must not start"),
    )

    with pytest.raises(SystemExit) as exc_info:
        smoke.main(argv)

    assert exc_info.value.code == 2
    assert capsys.readouterr().out.splitlines() == [
        "live_smoke_executed: no",
        "reason: invalid_duration",
    ]


def test_async_duration_contract_rejects_non_exact_or_out_of_range_values() -> None:
    for value in (True, 5.0, 4, 61):
        output: list[str] = []
        guarded = GuardedEnvironment({}, {smoke.RUN_GATE_ENV, smoke.API_KEY_ENV})
        result = asyncio.run(
            smoke.async_main(  # type: ignore[arg-type]
                seconds=value,
                environ=guarded,
                printer=output.append,
            )
        )
        assert result == 2
        assert output == [
            "live_smoke_executed: no",
            "reason: invalid_duration",
        ]


@pytest.mark.parametrize("gate", [None, "", "false", "1", "yes", "on", "true-ish"])
def test_non_true_gate_is_safe_disabled_without_key_access(gate: str | None) -> None:
    values = {} if gate is None else {smoke.RUN_GATE_ENV: gate}
    environ = GuardedEnvironment(values, {smoke.API_KEY_ENV})
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(
            environ=environ,
            printer=output.append,
            client_factory=lambda _config: pytest.fail("client must not be built"),
            pool_factory=lambda **_kwargs: pytest.fail("pool must not be built"),
            session_runner=lambda **_kwargs: pytest.fail("runner must not be called"),
            timeout_factory=lambda _seconds: pytest.fail("timeout must not start"),
        )
    )

    assert result == 0
    assert output == [
        "live_smoke_executed: no",
        "reason: opt_in_disabled",
    ]


@pytest.mark.parametrize("gate", ["true", " TRUE ", "TrUe"])
def test_normalized_exact_true_enables_smoke(gate: str) -> None:
    result, output, pool, timeout, runner_calls = _run(
        observations=(_observation("enabled"),),
        environ={smoke.RUN_GATE_ENV: gate, smoke.API_KEY_ENV: SECRET},
    )

    assert result == 0
    assert pool.snapshot_calls == 1
    assert timeout.entered == timeout.exited == 1
    assert len(runner_calls) == 1
    assert "result: success" in output


@pytest.mark.parametrize("key", [None, "", "   "])
def test_enabled_missing_key_fails_closed_before_construction(key: str | None) -> None:
    environ = {smoke.RUN_GATE_ENV: "true"}
    if key is not None:
        environ[smoke.API_KEY_ENV] = key
    output: list[str] = []

    result = asyncio.run(
        smoke.async_main(
            environ=environ,
            printer=output.append,
            client_factory=lambda _config: pytest.fail("client must not be built"),
            pool_factory=lambda **_kwargs: pytest.fail("pool must not be built"),
            session_runner=lambda **_kwargs: pytest.fail("runner must not be called"),
            timeout_factory=lambda _seconds: pytest.fail("timeout must not start"),
        )
    )

    assert result == 1
    assert output == [
        "live_smoke_executed: no",
        "reason: api_key_missing",
    ]


def test_composition_uses_existing_config_and_smoke_pool_constants() -> None:
    observed_configs: list[SteamApisWebSocketConfig] = []
    pool_calls: list[dict[str, object]] = []
    pool = FakePool((_observation("composition"),))

    def client_factory(config: SteamApisWebSocketConfig) -> SteamApisWebSocketClient:
        observed_configs.append(config)
        return SteamApisWebSocketClient(config, _connector=lambda *_a, **_kw: None)

    def pool_factory(**kwargs: object) -> FakePool:
        pool_calls.append(kwargs)
        return pool

    async def runner(**_kwargs: object) -> object:
        return object()

    result = asyncio.run(
        smoke.async_main(
            environ=_enabled_environment(f"  {SECRET}  "),
            client_factory=client_factory,
            pool_factory=pool_factory,  # type: ignore[arg-type]
            session_runner=runner,
            timeout_factory=lambda _seconds: FakeTimeout(),
        )
    )

    assert result == 0
    assert type(observed_configs[0]) is SteamApisWebSocketConfig
    assert observed_configs[0].api_key == SECRET
    assert SECRET not in repr(observed_configs[0])
    assert pool_calls == [
        {"max_size": 5_000, "ttl": timedelta(minutes=10)}
    ]


def test_normal_completion_runs_once_then_snapshots_once_and_counts_current_state() -> None:
    observations = (
        _observation("added"),
        _observation("updated", event_type=SteamApisListingEventType.UPDATED),
    )
    result, output, pool, timeout, runner_calls = _run(observations=observations)

    assert result == 0
    assert len(runner_calls) == 1
    assert pool.snapshot_calls == 1
    assert timeout.entered == timeout.exited == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: success",
        "stop_reason: normal_close",
        "duration_seconds: 15",
        "retained_observations: 2",
        "retained_added: 1",
        "retained_updated: 1",
    ]


def test_normal_completion_with_empty_snapshot_fails_without_retry() -> None:
    result, output, pool, _timeout, runner_calls = _run()

    assert result == 1
    assert len(runner_calls) == 1
    assert pool.snapshot_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: no_retained_observations",
        "stop_reason: normal_close",
        "duration_seconds: 15",
        "retained_observations: 0",
        "retained_added: 0",
        "retained_updated: 0",
    ]


def test_actual_timeout_cancels_runner_then_snapshots_current_pool_once() -> None:
    pool = FakePool((_observation("timeout"),))
    output: list[str] = []
    runner_calls = 0
    cancelled = False
    timeout_values: list[int] = []

    async def runner(**_kwargs: object) -> None:
        nonlocal runner_calls, cancelled
        runner_calls += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled = True
            raise

    def timeout_factory(seconds: float | None):
        timeout_values.append(int(seconds or 0))
        return asyncio.timeout(0.001)

    result = asyncio.run(
        smoke.async_main(
            seconds=23,
            environ=_enabled_environment(),
            printer=output.append,
            client_factory=lambda _config: object(),  # type: ignore[arg-type]
            pool_factory=lambda **_kwargs: pool,  # type: ignore[arg-type]
            session_runner=runner,
            timeout_factory=timeout_factory,
        )
    )

    assert result == 0
    assert runner_calls == 1
    assert cancelled is True
    assert timeout_values == [23]
    assert pool.snapshot_calls == 1
    assert "stop_reason: timeout" in output


def test_actual_timeout_with_empty_current_pool_fails_without_retry() -> None:
    pool = FakePool()
    calls = 0

    async def runner(**_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()

    output: list[str] = []
    result = asyncio.run(
        smoke.async_main(
            environ=_enabled_environment(),
            printer=output.append,
            client_factory=lambda _config: object(),  # type: ignore[arg-type]
            pool_factory=lambda **_kwargs: pool,  # type: ignore[arg-type]
            session_runner=runner,
            timeout_factory=lambda _seconds: asyncio.timeout(0.001),
        )
    )

    assert result == 1
    assert calls == 1
    assert pool.snapshot_calls == 1
    assert "reason: no_retained_observations" in output
    assert "stop_reason: timeout" in output


def test_runner_timeout_error_is_session_failure_not_expected_stop() -> None:
    result, output, pool, _timeout, runner_calls = _run(
        observations=(_observation("must-not-snapshot"),),
        session_error=TimeoutError("nested secret"),
    )

    assert result == 1
    assert len(runner_calls) == 1
    assert pool.snapshot_calls == 0
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: session_failed",
    ]


def test_ordinary_session_failure_is_fixed_safe_and_does_not_snapshot() -> None:
    sensitive = (
        f"{SECRET} wss://example.invalid?apiKey={SECRET} "
        "purchaseLink market_hash_name price float seed raw-json"
    )
    result, output, pool, _timeout, runner_calls = _run(
        observations=(_observation("retained-before-failure"),),
        session_error=RuntimeError(sensitive),
    )

    assert result == 1
    assert len(runner_calls) == 1
    assert pool.snapshot_calls == 0
    rendered = "\n".join(output)
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: session_failed",
    ]
    for prohibited in (SECRET, "wss://", "apiKey", "purchaseLink", "market_hash_name"):
        assert prohibited not in rendered


def test_snapshot_failure_is_fixed_safe_without_partial_counts() -> None:
    result, output, pool, _timeout, runner_calls = _run(
        observations=(_observation("sensitive"),),
        snapshot_error=RuntimeError(f"{SECRET} purchaseLink source-id price float"),
    )

    assert result == 1
    assert len(runner_calls) == 1
    assert pool.snapshot_calls == 1
    assert output == [
        "live_smoke_executed: yes",
        "result: failed",
        "reason: snapshot_failed",
    ]


@pytest.mark.parametrize(
    "error",
    [
        MemoryError(),
        asyncio.CancelledError(),
        KeyboardInterrupt(),
        ControlFlow(),
    ],
)
def test_session_process_control_exceptions_propagate_without_snapshot(
    error: BaseException,
) -> None:
    pool = FakePool((_observation("not-summarized"),))
    timeout = FakeTimeout()

    async def runner(**_kwargs: object) -> None:
        raise error

    with pytest.raises(type(error)) as exc_info:
        asyncio.run(
            smoke.async_main(
                environ=_enabled_environment(),
                client_factory=lambda _config: object(),  # type: ignore[arg-type]
                pool_factory=lambda **_kwargs: pool,  # type: ignore[arg-type]
                session_runner=runner,
                timeout_factory=lambda _seconds: timeout,
            )
        )

    assert exc_info.value is error
    assert pool.snapshot_calls == 0


@pytest.mark.parametrize("error", [MemoryError(), asyncio.CancelledError(), ControlFlow()])
def test_snapshot_process_control_exceptions_propagate(error: BaseException) -> None:
    pool = FakePool(snapshot_error=error)

    async def runner(**_kwargs: object) -> object:
        return object()

    with pytest.raises(type(error)) as exc_info:
        asyncio.run(
            smoke.async_main(
                environ=_enabled_environment(),
                client_factory=lambda _config: object(),  # type: ignore[arg-type]
                pool_factory=lambda **_kwargs: pool,  # type: ignore[arg-type]
                session_runner=runner,
                timeout_factory=lambda _seconds: FakeTimeout(),
            )
        )

    assert exc_info.value is error
    assert pool.snapshot_calls == 1


class FakeWebSocket:
    def __init__(self, frames: list[str], receive_error: BaseException) -> None:
        self._frames = frames
        self._receive_error = receive_error
        self._index = 0
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        if self._index < len(self._frames):
            frame = self._frames[self._index]
            self._index += 1
            return frame
        raise self._receive_error


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeWebSocket:
        self.entered += 1
        return self.websocket

    async def __aexit__(self, *_args: object) -> None:
        self.exited += 1


class FakeConnector:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, uri: str, **kwargs: object) -> FakeConnection:
        self.calls.append((uri, kwargs))
        return self.connection


def _offer_frame(token: str, event_type: str, timestamp: datetime, price: float) -> str:
    return json.dumps(
        {
            "type": "offer",
            "eventType": event_type,
            "marketplace": "Buff163",
            "game": "CS2",
            "timestamp": int(timestamp.timestamp() * 1_000),
            "data": {
                "name": f"Sensitive market {token}",
                "purchaseLink": f"https://example.invalid/live/{token}",
                "priceUSD": 1,
                "priceEUR": 1,
                "priceCNY": price,
                "priceRUB": 1,
                "daysTradeLocked": 0,
                "foundAt": int(timestamp.timestamp()),
                "inspectLink": f"steam://inspect/{token}",
                "float": 0.1,
                "paintIndex": 1,
                "paintSeed": 2,
                "stickers": [],
            },
        }
    )


def test_real_client_parser_runner_pool_offline_composition_is_single_and_safe() -> None:
    subscribed = json.dumps(
        {"type": "subscribed", "marketplaces": ["Buff163"], "games": ["CS2"]}
    )
    t0 = BASE_TIME
    frames = [
        subscribed,
        _offer_frame("A", "Added", t0 + timedelta(seconds=1), 10),
        _offer_frame("A", "Updated", t0 + timedelta(seconds=2), 11),
        _offer_frame("B", "Added", t0 + timedelta(seconds=3), 12),
        _offer_frame("A", "Updated", t0, 9),
    ]
    normal_close = ConnectionClosedOK(Close(1000, "normal"), Close(1000, "normal"), True)
    websocket = FakeWebSocket(frames, normal_close)
    connection = FakeConnection(websocket)
    connector = FakeConnector(connection)
    real_pool: SteamApisOfferPool | None = None
    runner_calls = 0
    output: list[str] = []

    def client_factory(config: SteamApisWebSocketConfig) -> SteamApisWebSocketClient:
        return SteamApisWebSocketClient(config, _connector=connector)

    def pool_factory(*, max_size: int, ttl: timedelta) -> SteamApisOfferPool:
        nonlocal real_pool
        real_pool = SteamApisOfferPool(max_size=max_size, ttl=ttl, now=lambda: t0)
        return real_pool

    async def runner(**kwargs: object) -> object:
        nonlocal runner_calls
        runner_calls += 1
        return await run_steamapis_offer_session(**kwargs)  # type: ignore[arg-type]

    result = asyncio.run(
        smoke.async_main(
            environ=_enabled_environment(SECRET),
            printer=output.append,
            client_factory=client_factory,
            pool_factory=pool_factory,
            session_runner=runner,
            timeout_factory=lambda _seconds: FakeTimeout(),
        )
    )

    assert result == 0
    assert runner_calls == 1
    assert len(connector.calls) == 1
    assert connection.entered == connection.exited == 1
    assert len(websocket.sent) == 1
    assert real_pool is not None
    rendered = "\n".join(output)
    assert "stop_reason: normal_close" in rendered
    assert "retained_observations: 2" in rendered
    assert "retained_added: 1" in rendered
    assert "retained_updated: 1" in rendered
    for prohibited in (
        SECRET,
        "apiKey",
        "Sensitive market",
        "example.invalid",
        "steam://",
        "source_offer_id",
        "price",
        "float",
        "seed",
    ):
        assert prohibited not in rendered


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_entrypoints_are_offline_and_safe(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_GATE_ENV, None)
    env[smoke.API_KEY_ENV] = "inherited-must-not-print"
    env["REDIS_URL"] = "redis://must-not-connect.invalid/15"
    command = (
        [sys.executable, "scripts/run_live_steamapis_offer_smoke.py"]
        if entrypoint == "direct"
        else [sys.executable, "-m", "scripts.run_live_steamapis_offer_smoke"]
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
    assert "inherited-must-not-print" not in combined
    assert "must-not-connect.invalid" not in combined


def test_smoke_script_architecture_is_thin_and_has_single_authority_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_live_steamapis_offer_smoke.py"
    )
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
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    forbidden_import_terms = {
        "live_pool_recipe_construction",
        "live_recipe_construction",
        "live_metadata_catalog",
        "steamapis_candidate_adapter",
        "recipe_solver",
        "valuation",
        "steamdt",
        "buff_client",
        "redis",
        "discord",
        "fastapi",
        "scheduler",
        "sqlalchemy",
        "app.config",
        "dotenv",
        "logging",
    }
    assert not any(
        term in imported
        for imported in imports
        for term in forbidden_import_terms
    )
    assert calls.count("session_runner") == 1
    assert calls.count("snapshot") == 1
    assert not any(isinstance(node, (ast.While, ast.AsyncFor)) for node in ast.walk(tree))
    forbidden_calls = {
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
        "get_observation",
        "get_purchase_link",
        "snapshot_candidates",
        "construct_live_recipes_from_pool",
        "construct_live_recipes",
        "classify_steamapis_snapshot",
        "parse_steamapis_message",
    }
    assert forbidden_calls.isdisjoint(calls)
    assert "wss://" not in source
    assert '"subscribeTo"' not in source
    assert "newFloorOnly" not in source
