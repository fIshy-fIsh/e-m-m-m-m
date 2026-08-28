from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

import app.services.steamapis_offer_session as session_module
from app.clients.steamapis_websocket_client import (
    SteamApisWebSocketClient,
    SteamApisWebSocketClientError,
    SteamApisWebSocketConfig,
)
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
    parse_steamapis_message,
)
from app.services.steamapis_offer_pool import SteamApisOfferPool, SteamApisOfferPoolError
from app.services.steamapis_offer_session import (
    SteamApisOfferSessionError,
    SteamApisOfferSessionResult,
    run_steamapis_offer_session,
)

BASE_TIME = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
DEFAULT_NOW = BASE_TIME + timedelta(minutes=5)
DEFAULT_TTL = timedelta(hours=1)
FIXED_ERROR = "SteamApis offer session failed"
DUMMY_KEY = "dummy-session-key-not-real"
OFFICIAL_ENDPOINT = "wss://marketplaceapi.steamapis.com/ws/v2/offers"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamapis_offer_session.py"
)


class FakeClient:
    def __init__(
        self,
        observations: tuple[SteamApisListingObservation, ...] = (),
        *,
        error: BaseException | None = None,
    ) -> None:
        self.observations = observations
        self.error = error
        self.iterator_calls = 0
        self.yielded = 0

    async def iter_observations(self) -> AsyncIterator[SteamApisListingObservation]:
        self.iterator_calls += 1
        for observation in self.observations:
            self.yielded += 1
            yield observation
        if self.error is not None:
            raise self.error


class RecordingPool:
    def __init__(self, *, error_at: int | None = None, error: BaseException | None = None):
        self.error_at = error_at
        self.error = error
        self.ingested: list[SteamApisListingObservation] = []
        self.calls = 0

    def ingest(self, observation: SteamApisListingObservation) -> None:
        self.calls += 1
        if self.calls == self.error_at and self.error is not None:
            raise self.error
        self.ingested.append(observation)


class FakeWebSocket:
    def __init__(
        self,
        frames: list[object],
        *,
        receive_error: BaseException | None = None,
    ) -> None:
        self.frames = list(frames)
        self.receive_error = receive_error
        self.sent: list[str] = []
        self._index = 0

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self) -> AsyncIterator[object]:
        return self

    async def __anext__(self) -> object:
        if self._index < len(self.frames):
            frame = self.frames[self._index]
            self._index += 1
            return frame
        if self.receive_error is not None:
            raise self.receive_error
        raise StopAsyncIteration


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


class IntSubclass(int):
    pass


class DirectBaseException(BaseException):
    pass


def _observation(
    *,
    link_suffix: str = "a",
    event_type: SteamApisListingEventType = SteamApisListingEventType.ADDED,
    price_cny: Decimal = Decimal("100.00"),
    message_timestamp: datetime = BASE_TIME,
) -> SteamApisListingObservation:
    purchase_link = f"https://example.invalid/manual/{link_suffix}"
    return SteamApisListingObservation(
        source_offer_id=make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            purchase_link,
        ),
        event_type=event_type,
        marketplace="Buff163",
        game="CS2",
        market_hash_name="AK-47 | Synthetic (Field-Tested)",
        purchase_link=purchase_link,
        inspect_link="steam://inspect/synthetic",
        price_cny=price_cny,
        float_value=Decimal("0.1234"),
        paint_index=282,
        paint_seed=321,
        days_trade_locked=0,
        found_at=message_timestamp - timedelta(minutes=1),
        message_timestamp=message_timestamp,
        stickers=(),
    )


def _pool(
    *,
    max_size: int = 10,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime = DEFAULT_NOW,
) -> SteamApisOfferPool:
    return SteamApisOfferPool(max_size=max_size, ttl=ttl, now=lambda: now)


def _offer_frame(
    *,
    link_suffix: str,
    event_type: str,
    timestamp: datetime,
    price_cny: float,
) -> str:
    timestamp_ms = int(timestamp.timestamp() * 1000)
    return json.dumps(
        {
            "type": "offer",
            "eventType": event_type,
            "marketplace": "Buff163",
            "game": "CS2",
            "timestamp": timestamp_ms,
            "data": {
                "name": "AK-47 | Synthetic (Field-Tested)",
                "purchaseLink": f"https://example.invalid/manual/{link_suffix}",
                "priceUSD": 15.0,
                "priceEUR": 14.0,
                "priceCNY": price_cny,
                "priceRUB": 1400.0,
                "daysTradeLocked": 0,
                "foundAt": int(timestamp.timestamp()) - 60,
                "inspectLink": "steam://inspect/synthetic",
                "float": 0.1234,
                "paintIndex": 282,
                "paintSeed": 321,
                "stickers": None,
            },
        }
    )


def _run(
    client: SteamApisWebSocketClient,
    pool: SteamApisOfferPool,
) -> SteamApisOfferSessionResult:
    return asyncio.run(run_steamapis_offer_session(client=client, pool=pool))


def _run_duck(client: object, pool: object) -> SteamApisOfferSessionResult:
    return asyncio.run(
        run_steamapis_offer_session(
            client=client,  # type: ignore[arg-type]
            pool=pool,  # type: ignore[arg-type]
        )
    )


def _assert_fixed_error(client: object, pool: object) -> SteamApisOfferSessionError:
    with pytest.raises(SteamApisOfferSessionError) as exc_info:
        _run_duck(client, pool)
    assert str(exc_info.value) == FIXED_ERROR
    assert repr(exc_info.value) == f"SteamApisOfferSessionError('{FIXED_ERROR}')"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    return exc_info.value


def test_public_api_and_signature_are_small_and_exact() -> None:
    assert session_module.__all__ == (
        "SteamApisOfferSessionError",
        "SteamApisOfferSessionResult",
        "run_steamapis_offer_session",
    )
    assert [field.name for field in fields(SteamApisOfferSessionResult)] == [
        "observations_consumed"
    ]
    parameters = list(signature(run_steamapis_offer_session).parameters.values())
    assert [(value.name, value.kind) for value in parameters] == [
        ("client", Parameter.KEYWORD_ONLY),
        ("pool", Parameter.KEYWORD_ONLY),
    ]
    assert get_type_hints(run_steamapis_offer_session) == {
        "client": SteamApisWebSocketClient,
        "pool": SteamApisOfferPool,
        "return": SteamApisOfferSessionResult,
    }


def test_result_is_frozen_keyword_only_and_repr_hidden() -> None:
    result = SteamApisOfferSessionResult(observations_consumed=3)

    assert result.observations_consumed == 3
    assert "observations_consumed" not in repr(result)
    with pytest.raises(TypeError):
        SteamApisOfferSessionResult(3)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.observations_consumed = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [-1, True, 1.0, "1", None, IntSubclass(1)],
)
def test_result_rejects_invalid_counts_with_fixed_error(value: object) -> None:
    with pytest.raises(SteamApisOfferSessionError) as exc_info:
        SteamApisOfferSessionResult(
            observations_consumed=value,  # type: ignore[arg-type]
        )

    assert str(exc_info.value) == FIXED_ERROR
    assert exc_info.value.__cause__ is None


def test_normal_empty_session_returns_zero_and_calls_iterator_once() -> None:
    client = FakeClient()
    pool = RecordingPool()

    result = _run_duck(client, pool)

    assert result.observations_consumed == 0
    assert client.iterator_calls == 1
    assert pool.calls == 0


def test_one_observation_is_ingested_and_counted() -> None:
    observation = _observation()
    client = FakeClient((observation,))
    pool = _pool()

    result = _run_duck(client, pool)

    assert result.observations_consumed == 1
    assert pool.snapshot().observations == (observation,)


def test_multiple_observations_reach_ingest_in_exact_yield_order() -> None:
    observations = tuple(_observation(link_suffix=str(index)) for index in range(4))
    client = FakeClient(observations)
    pool = RecordingPool()

    result = _run_duck(client, pool)

    assert result.observations_consumed == 4
    assert pool.ingested == list(observations)
    assert client.iterator_calls == 1


def test_added_then_newer_updated_retains_newer_and_counts_both() -> None:
    added = _observation()
    updated = _observation(
        event_type=SteamApisListingEventType.UPDATED,
        price_cny=Decimal("90.00"),
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    pool = _pool()

    result = _run_duck(FakeClient((added, updated)), pool)

    assert result.observations_consumed == 2
    assert pool.snapshot().observations == (updated,)


def test_older_updated_is_consumed_without_regressing_pool_state() -> None:
    newer = _observation(message_timestamp=BASE_TIME + timedelta(minutes=1))
    older = _observation(
        event_type=SteamApisListingEventType.UPDATED,
        price_cny=Decimal("1.00"),
        message_timestamp=BASE_TIME,
    )
    pool = _pool()

    result = _run_duck(FakeClient((newer, older)), pool)

    assert result.observations_consumed == 2
    assert pool.snapshot().observations == (newer,)


def test_identical_replay_is_consumed_without_claiming_a_second_retention() -> None:
    observation = _observation()
    pool = _pool()

    result = _run_duck(FakeClient((observation, observation)), pool)

    assert result.observations_consumed == 2
    assert pool.snapshot().observations == (observation,)


def test_expired_observation_is_consumed_but_pool_does_not_retain_it() -> None:
    expired = _observation(message_timestamp=BASE_TIME - timedelta(hours=2))
    pool = _pool(ttl=timedelta(minutes=10))

    result = _run_duck(FakeClient((expired,)), pool)

    assert result.observations_consumed == 1
    assert pool.snapshot().observations == ()


def test_capacity_retention_remains_authoritative_in_pool() -> None:
    observations = tuple(
        _observation(
            link_suffix=str(index),
            message_timestamp=BASE_TIME + timedelta(minutes=index),
        )
        for index in range(3)
    )
    pool = _pool(max_size=2, now=BASE_TIME + timedelta(minutes=4))

    result = _run_duck(FakeClient(observations), pool)

    assert result.observations_consumed == 3
    assert set(pool.snapshot().observations) == set(observations[-2:])


def test_equal_timestamp_conflict_fails_and_preserves_first_mutation() -> None:
    original = _observation()
    conflicting = _observation(
        event_type=SteamApisListingEventType.UPDATED,
        price_cny=Decimal("1.00"),
    )
    pool = _pool()

    _assert_fixed_error(FakeClient((original, conflicting)), pool)

    assert pool.snapshot().observations == (original,)


def test_client_failure_after_success_keeps_prior_mutations_without_result() -> None:
    first = _observation(link_suffix="first")
    second = _observation(link_suffix="second")
    error = SteamApisWebSocketClientError()
    client = FakeClient((first, second), error=error)
    pool = _pool()

    _assert_fixed_error(client, pool)

    assert set(pool.snapshot().observations) == {first, second}
    assert client.iterator_calls == 1


def test_pool_failure_after_success_keeps_prior_mutation() -> None:
    first = _observation(link_suffix="first")
    second = _observation(link_suffix="second")
    pool = RecordingPool(error_at=2, error=SteamApisOfferPoolError())

    _assert_fixed_error(FakeClient((first, second)), pool)

    assert pool.ingested == [first]
    assert pool.calls == 2


@pytest.mark.parametrize("failure_stage", ["client", "pool"])
def test_ordinary_nested_failure_details_are_redacted(failure_stage: str) -> None:
    sensitive = (
        "apiKey=dummy-leak wss://secret.invalid/query "
        "source-id purchaseLink inspectLink market-name price=1 float=.1 seed=7"
    )
    observation = _observation()
    if failure_stage == "client":
        client: object = FakeClient(error=RuntimeError(sensitive))
        pool: object = RecordingPool()
    else:
        client = FakeClient((observation,))
        pool = RecordingPool(error_at=1, error=RuntimeError(sensitive))

    error = _assert_fixed_error(client, pool)

    rendered = f"{error!s} {error!r}"
    for fragment in sensitive.split():
        assert fragment not in rendered


@pytest.mark.parametrize(
    "error",
    [MemoryError("memory"), asyncio.CancelledError("cancel")],
)
@pytest.mark.parametrize("failure_stage", ["client", "pool"])
def test_memory_and_cancellation_propagate_by_identity(
    failure_stage: str,
    error: BaseException,
) -> None:
    observation = _observation()
    if failure_stage == "client":
        client: object = FakeClient((observation,), error=error)
        pool: object = RecordingPool()
    else:
        client = FakeClient((observation,))
        pool = RecordingPool(error_at=1, error=error)

    with pytest.raises(type(error)) as exc_info:
        _run_duck(client, pool)

    assert exc_info.value is error


@pytest.mark.parametrize(
    "error",
    [KeyboardInterrupt("interrupt"), DirectBaseException("direct")],
)
def test_other_base_exceptions_propagate_by_identity(error: BaseException) -> None:
    client = FakeClient(error=error)

    with pytest.raises(type(error)) as exc_info:
        _run_duck(client, RecordingPool())

    assert exc_info.value is error


def test_real_client_subscribed_then_normal_close_returns_empty_result() -> None:
    normal_close = ConnectionClosedOK(Close(1000, "normal"), Close(1000, "normal"), True)
    websocket = FakeWebSocket(
        [json.dumps({"type": "subscribed"})],
        receive_error=normal_close,
    )
    connection = FakeConnection(websocket)
    connector = FakeConnector(connection)
    client = SteamApisWebSocketClient(
        SteamApisWebSocketConfig(api_key=DUMMY_KEY),
        _connector=connector,
    )
    pool = _pool()

    result = _run(client, pool)

    assert result.observations_consumed == 0
    assert pool.snapshot().observations == ()
    assert len(connector.calls) == 1
    assert len(websocket.sent) == 1


def test_real_client_parser_pool_runner_end_to_end_is_ordered_and_offline() -> None:
    added_a = _offer_frame(
        link_suffix="a",
        event_type="Added",
        timestamp=BASE_TIME + timedelta(minutes=1),
        price_cny=100.0,
    )
    updated_a = _offer_frame(
        link_suffix="a",
        event_type="Updated",
        timestamp=BASE_TIME + timedelta(minutes=2),
        price_cny=90.0,
    )
    added_b = _offer_frame(
        link_suffix="b",
        event_type="Added",
        timestamp=BASE_TIME + timedelta(minutes=3),
        price_cny=110.0,
    )
    older_a = _offer_frame(
        link_suffix="a",
        event_type="Updated",
        timestamp=BASE_TIME,
        price_cny=1.0,
    )
    normal_close = ConnectionClosedOK(Close(1000, "normal"), Close(1000, "normal"), True)
    websocket = FakeWebSocket(
        [
            json.dumps({"type": "subscribed"}),
            added_a,
            updated_a,
            added_b,
            older_a,
        ],
        receive_error=normal_close,
    )
    connection = FakeConnection(websocket)
    connector = FakeConnector(connection)
    client = SteamApisWebSocketClient(
        SteamApisWebSocketConfig(api_key=DUMMY_KEY),
        _connector=connector,
    )
    pool = _pool(now=BASE_TIME + timedelta(minutes=4))

    result = _run(client, pool)

    parsed_updated_a = parse_steamapis_message(updated_a).offer
    parsed_added_b = parse_steamapis_message(added_b).offer
    assert parsed_updated_a is not None
    assert parsed_added_b is not None
    assert result.observations_consumed == 4
    assert set(pool.snapshot().observations) == {parsed_updated_a, parsed_added_b}
    assert pool.get_observation(parsed_updated_a.source_offer_id) == parsed_updated_a
    assert pool.get_purchase_link(parsed_updated_a.source_offer_id) == (
        parsed_updated_a.purchase_link
    )
    assert len(connector.calls) == 1
    assert connector.calls[0][0] == f"{OFFICIAL_ENDPOINT}?apiKey={DUMMY_KEY}"
    assert connection.entered == 1
    assert connection.exited == 1
    assert len(websocket.sent) == 1


def test_real_client_abnormal_close_after_ingests_fails_without_reconnect() -> None:
    added_a = _offer_frame(
        link_suffix="a",
        event_type="Added",
        timestamp=BASE_TIME,
        price_cny=100.0,
    )
    added_b = _offer_frame(
        link_suffix="b",
        event_type="Added",
        timestamp=BASE_TIME + timedelta(minutes=1),
        price_cny=110.0,
    )
    abnormal_close = ConnectionClosedError(
        Close(1008, "apiKey=reflected-secret"),
        Close(1008, "apiKey=reflected-secret"),
        True,
    )
    websocket = FakeWebSocket(
        [json.dumps({"type": "subscribed"}), added_a, added_b],
        receive_error=abnormal_close,
    )
    connection = FakeConnection(websocket)
    connector = FakeConnector(connection)
    client = SteamApisWebSocketClient(
        SteamApisWebSocketConfig(api_key=DUMMY_KEY),
        _connector=connector,
    )
    pool = _pool()

    error = _assert_fixed_error(client, pool)

    assert "reflected-secret" not in f"{error!s} {error!r}"
    assert len(pool.snapshot().observations) == 2
    assert len(connector.calls) == 1
    assert len(websocket.sent) == 1


def test_equivalent_sessions_are_deterministic_on_fresh_pools() -> None:
    observations = (
        _observation(link_suffix="a"),
        _observation(
            link_suffix="b",
            message_timestamp=BASE_TIME + timedelta(minutes=1),
        ),
    )
    first_pool = _pool()
    second_pool = _pool()

    first = _run_duck(FakeClient(observations), first_pool)
    second = _run_duck(FakeClient(observations), second_pool)

    assert first.observations_consumed == second.observations_consumed == 2
    assert first_pool.snapshot() == second_pool.snapshot()


def test_architecture_is_one_sequential_ingest_without_forbidden_boundaries() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert imports == {
        "__future__",
        "asyncio",
        "dataclasses",
        "app.clients.steamapis_websocket_client",
        "app.services.steamapis_offer_pool",
    }
    assert calls.count("iter_observations") == 1
    assert calls.count("ingest") == 1
    assert "parse_steamapis_message" not in source
    assert "source_offer_id" not in source
    assert "purchase_link" not in source
    assert "message_timestamp" not in source
    forbidden_calls = {
        "snapshot",
        "get_observation",
        "get_purchase_link",
        "snapshot_candidates",
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
    }
    assert forbidden_calls.isdisjoint(calls)
    forbidden_import_fragments = {
        "candidate",
        "metadata",
        "construction",
        "solver",
        "valuation",
        "ev_service",
        "risk",
        "steamdt",
        "buff",
        "redis",
        "discord",
        "fastapi",
        "sqlalchemy",
        "scheduler",
        "config",
        "logging",
        "os",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_import_fragments
    )
    assert "while " not in source
    assert "asyncio.create_task" not in source
    assert "asyncio.gather" not in source
