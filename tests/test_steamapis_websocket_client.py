from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, fields
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from app.clients.steamapis_websocket_client import (
    SteamApisWebSocketClient,
    SteamApisWebSocketClientError,
    SteamApisWebSocketConfig,
)
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    SteamApisMessageKind,
    parse_steamapis_message,
)

MODULE_PATH = (
    Path(__file__).parents[1] / "app" / "clients" / "steamapis_websocket_client.py"
)
DUMMY_KEY = "dummy key+/not-a-real-secret"
OFFICIAL_ENDPOINT = "wss://marketplaceapi.steamapis.com/ws/v2/offers"
FIXED_ERROR = "SteamApis WebSocket session failed"


def _offer_payload(*, event_type: str = "Added", price_cny: float = 109.125) -> str:
    return json.dumps(
        {
            "type": "offer",
            "eventType": event_type,
            "marketplace": "Buff163",
            "game": "CS2",
            "timestamp": 1_721_234_567_890,
            "data": {
                "name": "AK-47 | Redline (Field-Tested)",
                "purchaseLink": "https://example.test/manual/opaque-offer",
                "priceUSD": 15.25,
                "priceEUR": 14.2,
                "priceCNY": price_cny,
                "priceRUB": 1400,
                "daysTradeLocked": 0,
                "foundAt": 1_721_234_500,
                "inspectLink": "steam://inspect/example",
                "float": 0.123456,
                "paintIndex": 282,
                "paintSeed": 321,
                "stickers": None,
            },
        }
    )


class FakeWebSocket:
    def __init__(
        self,
        frames: list[object] | None = None,
        *,
        send_error: BaseException | None = None,
        receive_error: BaseException | None = None,
    ) -> None:
        self.frames = list(frames or [])
        self.send_error = send_error
        self.receive_error = receive_error
        self.sent: list[str] = []
        self._index = 0

    async def send(self, message: str) -> None:
        if self.send_error is not None:
            raise self.send_error
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
    def __init__(
        self,
        websocket: FakeWebSocket,
        *,
        enter_error: BaseException | None = None,
        exit_error: BaseException | None = None,
    ) -> None:
        self.websocket = websocket
        self.enter_error = enter_error
        self.exit_error = exit_error
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeWebSocket:
        self.entered += 1
        if self.enter_error is not None:
            raise self.enter_error
        return self.websocket

    async def __aexit__(self, *_args: object) -> None:
        self.exited += 1
        if self.exit_error is not None:
            raise self.exit_error


class FakeConnector:
    def __init__(
        self,
        connection: FakeConnection | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.connection = connection
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, uri: str, **kwargs: object) -> FakeConnection:
        self.calls.append((uri, kwargs))
        if self.error is not None:
            raise self.error
        assert self.connection is not None
        return self.connection


def _client(
    frames: list[object] | None = None,
    *,
    connector_error: BaseException | None = None,
    enter_error: BaseException | None = None,
    send_error: BaseException | None = None,
    receive_error: BaseException | None = None,
    exit_error: BaseException | None = None,
) -> tuple[SteamApisWebSocketClient, FakeConnector, FakeWebSocket, FakeConnection]:
    websocket = FakeWebSocket(
        frames,
        send_error=send_error,
        receive_error=receive_error,
    )
    connection = FakeConnection(
        websocket,
        enter_error=enter_error,
        exit_error=exit_error,
    )
    connector = FakeConnector(connection, error=connector_error)
    client = SteamApisWebSocketClient(
        SteamApisWebSocketConfig(api_key=DUMMY_KEY),
        _connector=connector,
    )
    return client, connector, websocket, connection


async def _collect(client: SteamApisWebSocketClient) -> list[SteamApisListingObservation]:
    return [observation async for observation in client.iter_observations()]


def _run(client: SteamApisWebSocketClient) -> list[SteamApisListingObservation]:
    return asyncio.run(_collect(client))


def _assert_fixed_error(client: SteamApisWebSocketClient) -> SteamApisWebSocketClientError:
    with pytest.raises(SteamApisWebSocketClientError) as exc_info:
        _run(client)
    assert str(exc_info.value) == FIXED_ERROR
    assert repr(exc_info.value) == f"SteamApisWebSocketClientError('{FIXED_ERROR}')"
    assert exc_info.value.__cause__ is None
    return exc_info.value


def test_public_api_fields_and_signature_are_exact() -> None:
    assert [field.name for field in fields(SteamApisWebSocketConfig)] == [
        "api_key",
        "endpoint",
    ]
    parameters = list(signature(SteamApisWebSocketClient.iter_observations).parameters.values())
    assert [(parameter.name, parameter.kind) for parameter in parameters] == [
        ("self", Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return_hint = get_type_hints(SteamApisWebSocketClient.iter_observations)["return"]
    assert return_hint == AsyncIterator[SteamApisListingObservation]


def test_config_is_frozen_keyword_only_and_secret_repr_hidden() -> None:
    config = SteamApisWebSocketConfig(api_key=DUMMY_KEY)
    client = SteamApisWebSocketClient(config, _connector=FakeConnector(error=RuntimeError()))

    with pytest.raises(TypeError):
        SteamApisWebSocketConfig(DUMMY_KEY)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        config.api_key = "changed"  # type: ignore[misc]
    assert DUMMY_KEY not in repr(config)
    assert DUMMY_KEY not in repr(client)
    assert "api_key" not in repr(config)
    assert "api_key" not in repr(client)


@pytest.mark.parametrize("api_key", ["", " ", "\t\n", None, 1, True])
def test_blank_or_nonexact_api_key_fails_closed(api_key: object) -> None:
    with pytest.raises(SteamApisWebSocketClientError) as exc_info:
        SteamApisWebSocketConfig(api_key=api_key)  # type: ignore[arg-type]
    assert str(exc_info.value) == FIXED_ERROR
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "wss://example.test/ws/v2/offers",
        OFFICIAL_ENDPOINT + "/",
        OFFICIAL_ENDPOINT + "?future=1",
        " WSS://marketplaceapi.steamapis.com/ws/v2/offers ",
        None,
    ],
)
def test_only_exact_official_endpoint_is_allowed(endpoint: object) -> None:
    with pytest.raises(SteamApisWebSocketClientError):
        SteamApisWebSocketConfig(api_key=DUMMY_KEY, endpoint=endpoint)  # type: ignore[arg-type]


def test_connector_uri_options_and_subscription_are_exact_and_single() -> None:
    client, connector, websocket, connection = _client(
        [json.dumps({"type": "subscribed"})]
    )

    assert _run(client) == []

    assert connector.calls == [
        (
            OFFICIAL_ENDPOINT + "?apiKey=dummy+key%2B%2Fnot-a-real-secret",
            {
                "compression": "deflate",
                "open_timeout": 10,
                "max_size": 1_048_576,
            },
        )
    ]
    assert connection.entered == 1
    assert connection.exited == 1
    assert len(websocket.sent) == 1
    assert websocket.sent[0] == (
        '{"subscribeTo":["Buff163"],"games":["CS2"],"newFloorOnly":false}'
    )
    assert json.loads(websocket.sent[0]) == {
        "subscribeTo": ["Buff163"],
        "games": ["CS2"],
        "newFloorOnly": False,
    }
    assert "all" not in websocket.sent[0].lower()


def test_client_is_lazy_until_iterator_is_consumed() -> None:
    client, connector, websocket, connection = _client()

    iterator = client.iter_observations()

    assert connector.calls == []
    assert websocket.sent == []
    assert connection.entered == 0
    asyncio.run(iterator.aclose())


def test_subscribed_then_added_offer_yields_exact_parser_observation() -> None:
    offer_frame = _offer_payload()
    expected = parse_steamapis_message(offer_frame)
    assert expected.kind is SteamApisMessageKind.OFFER
    client, connector, _websocket, _connection = _client(
        [json.dumps({"type": "subscribed", "marketplaces": ["Buff163"]}), offer_frame]
    )

    result = _run(client)

    assert len(result) == 1
    assert type(result[0]) is SteamApisListingObservation
    assert result[0] == expected.offer
    assert result[0] is not expected.offer
    assert result[0].event_type is SteamApisListingEventType.ADDED
    assert len(connector.calls) == 1


def test_multiple_added_and_updated_offers_preserve_receive_order_and_identity() -> None:
    added = _offer_payload(event_type="Added", price_cny=100.0)
    updated = _offer_payload(event_type="Updated", price_cny=99.0)
    client, _connector, _websocket, _connection = _client(
        [json.dumps({"type": "subscribed"}), added, updated]
    )

    result = _run(client)

    assert [value.event_type for value in result] == [
        SteamApisListingEventType.ADDED,
        SteamApisListingEventType.UPDATED,
    ]
    assert result[0].source_offer_id == result[1].source_offer_id
    assert result[0] == parse_steamapis_message(added).offer
    assert result[1] == parse_steamapis_message(updated).offer


def test_ignored_parser_outcomes_do_not_yield() -> None:
    ignored = json.loads(_offer_payload())
    ignored["marketplace"] = "OtherMarket"
    client, _connector, _websocket, _connection = _client(
        [json.dumps({"type": "subscribed"}), json.dumps(ignored)]
    )

    assert _run(client) == []


def test_offer_before_subscribed_fails_closed_without_yield() -> None:
    client, connector, _websocket, _connection = _client([_offer_payload()])

    _assert_fixed_error(client)

    assert len(connector.calls) == 1


def test_server_error_discards_sensitive_text_and_fails_closed() -> None:
    secret = "apiKey=server-reflected-secret wss://secret.example/query"
    client, connector, _websocket, _connection = _client(
        [json.dumps({"type": "error", "error": secret})]
    )

    error = _assert_fixed_error(client)

    public = f"{error!s} {error!r}"
    assert secret not in public
    assert DUMMY_KEY not in public
    assert OFFICIAL_ENDPOINT not in public
    assert len(connector.calls) == 1


@pytest.mark.parametrize("frame", ["not-json", json.dumps({"type": "future"}), b"binary"])
def test_malformed_unknown_and_binary_frames_fail_closed(frame: object) -> None:
    client, connector, _websocket, _connection = _client([frame])

    _assert_fixed_error(client)

    assert len(connector.calls) == 1


def test_normal_close_exception_ends_iterator_without_reconnect() -> None:
    normal_close = ConnectionClosedOK(Close(1000, "normal"), Close(1000, "normal"), True)
    client, connector, websocket, connection = _client(receive_error=normal_close)

    assert _run(client) == []
    assert len(connector.calls) == 1
    assert len(websocket.sent) == 1
    assert connection.entered == 1
    assert connection.exited == 1


def test_abnormal_close_is_fixed_error_without_reconnect() -> None:
    abnormal_close = ConnectionClosedError(
        Close(1008, "apiKey=reflected-secret"),
        Close(1008, "apiKey=reflected-secret"),
        True,
    )
    client, connector, websocket, connection = _client(receive_error=abnormal_close)

    error = _assert_fixed_error(client)

    assert "reflected-secret" not in f"{error!s} {error!r}"
    assert len(connector.calls) == 1
    assert len(websocket.sent) == 1
    assert connection.entered == 1
    assert connection.exited == 1


@pytest.mark.parametrize("stage", ["connector", "enter", "send", "receive", "exit"])
def test_ordinary_session_failures_are_fixed_and_unchained(stage: str) -> None:
    secret = RuntimeError("apiKey=ordinary-secret " + OFFICIAL_ENDPOINT)
    kwargs: dict[str, BaseException] = {f"{stage}_error": secret}
    client, connector, _websocket, _connection = _client(**kwargs)

    error = _assert_fixed_error(client)

    assert "ordinary-secret" not in f"{error!s} {error!r}"
    assert OFFICIAL_ENDPOINT not in f"{error!s} {error!r}"
    assert len(connector.calls) == 1


@pytest.mark.parametrize(
    "error",
    [MemoryError("memory"), KeyboardInterrupt("interrupt"), asyncio.CancelledError("cancel")],
)
@pytest.mark.parametrize("stage", ["connector", "enter", "send", "receive", "exit"])
def test_nonordinary_failures_propagate_by_identity(stage: str, error: BaseException) -> None:
    kwargs: dict[str, BaseException] = {f"{stage}_error": error}
    client, connector, _websocket, _connection = _client(**kwargs)

    with pytest.raises(type(error)) as exc_info:
        _run(client)

    assert exc_info.value is error
    assert len(connector.calls) == 1


def test_architecture_reuses_parser_and_has_no_forbidden_boundaries() -> None:
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

    assert "app.services.steamapis_listing" in imports
    assert calls.count("parse_steamapis_message") == 1
    assert calls.count("send") == 1
    assert calls.count("_connector") == 1
    forbidden_import_fragments = {
        "steamapis_offer_pool",
        "steamapis_candidate_adapter",
        "live_metadata_catalog",
        "live_recipe_construction",
        "live_recipe_valuation",
        "recipe_solver",
        "steamdt",
        "buff",
        "redis",
        "discord",
        "fastapi",
        "sqlalchemy",
        "os",
        "logging",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_import_fragments
    )
    forbidden_calls = {
        "create_task",
        "ensure_future",
        "sleep",
        "solve_recipes",
        "construct_recipes",
        "ingest",
        "getenv",
    }
    assert forbidden_calls.isdisjoint(calls)
    assert "while True" not in source
    assert "async for connection in connect" not in source
    assert "Sec-WebSocket-Extensions" not in source
    assert "purchaseLink" not in source
    assert "source_offer_id" not in source
    assert "price_cny" not in source
