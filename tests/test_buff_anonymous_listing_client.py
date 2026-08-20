from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import httpx
import pytest

from app.clients.buff_anonymous_listing_client import (
    BUFF_ANONYMOUS_BASE_URL,
    BUFF_ANONYMOUS_SELL_ORDER_PATH,
    BUFF_ANONYMOUS_USER_AGENT,
    BuffAnonymousListingHttpClient,
    BuffAnonymousListingRequestError,
)

GOODS_ID = "goods-synthetic-1"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real network is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


class Transport(httpx.AsyncBaseTransport):
    def __init__(self, status: int = 200, body: bytes = b'{"code":"OK"}') -> None:
        self.status = status
        self.body = body
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=self.body, request=request)

    async def aclose(self) -> None:
        self.closed = True


def _client(transport: Transport) -> tuple[httpx.AsyncClient, BuffAnonymousListingHttpClient]:
    http_client = httpx.AsyncClient(
        base_url=BUFF_ANONYMOUS_BASE_URL,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        headers={"Accept": "application/json", "User-Agent": BUFF_ANONYMOUS_USER_AGENT},
    )
    return http_client, BuffAnonymousListingHttpClient(http_client)


def test_exact_request_and_detached_bytes() -> None:
    transport = Transport(body=b"payload")
    http_client, client = _client(transport)
    try:
        result = asyncio.run(client.fetch_sell_order_payload(GOODS_ID))
    finally:
        asyncio.run(http_client.aclose())

    assert result == b"payload"
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.path == BUFF_ANONYMOUS_SELL_ORDER_PATH
    assert list(request.url.params.multi_items()) == [
        ("game", "csgo"),
        ("goods_id", GOODS_ID),
        ("page_num", "1"),
        ("sort_by", "default"),
    ]
    assert request.content == b""
    assert request.headers["User-Agent"] == BUFF_ANONYMOUS_USER_AGENT
    assert request.headers["Accept"] == "application/json"
    assert not {
        "cookie",
        "authorization",
        "proxy-authorization",
        "device-id",
        "x-csrftoken",
        "referer",
        "origin",
        "x-requested-with",
    }.intersection(name.casefold() for name in request.headers)
    assert transport.closed is True


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_non_success_status_is_fixed(status: int) -> None:
    transport = Transport(status=status, body=b"private response")
    http_client, client = _client(transport)
    try:
        with pytest.raises(BuffAnonymousListingRequestError) as captured:
            asyncio.run(client.fetch_sell_order_payload(GOODS_ID))
    finally:
        asyncio.run(http_client.aclose())

    assert str(captured.value) == "anonymous BUFF listing request failed"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert len(transport.requests) == 1
    assert "private response" not in repr(captured.value)


@pytest.mark.parametrize("goods_id", ["", "   ", None, 1, True])
def test_invalid_goods_id_stops_before_transport(goods_id: object) -> None:
    transport = Transport()
    http_client, client = _client(transport)
    try:
        with pytest.raises(BuffAnonymousListingRequestError):
            asyncio.run(client.fetch_sell_order_payload(goods_id))  # type: ignore[arg-type]
    finally:
        asyncio.run(http_client.aclose())
    assert transport.requests == []


def test_hostile_client_defaults_do_not_enter_request() -> None:
    transport = Transport()
    auth_calls: list[httpx.Request] = []

    class HeaderAuth(httpx.Auth):
        def auth_flow(self, request: httpx.Request):
            auth_calls.append(request)
            request.headers["Authorization"] = "Bearer token-secret"
            yield request

    http_client = httpx.AsyncClient(
        base_url="https://wrong.invalid/private",
        params={"attacker": "query"},
        headers={
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "X-API-Key": "api-secret",
            "X-CSRF-Token": "csrf-secret",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://wrong.invalid",
        },
        cookies={"session": "secret"},
        auth=HeaderAuth(),
        follow_redirects=True,
        transport=transport,
    )
    client = BuffAnonymousListingHttpClient(http_client)
    try:
        asyncio.run(client.fetch_sell_order_payload(GOODS_ID))
    finally:
        asyncio.run(http_client.aclose())
    assert auth_calls == []
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.url.host == "buff.163.com"
    assert list(request.url.params) == ["game", "goods_id", "page_num", "sort_by"]
    assert set(name.casefold() for name in request.headers) == {
        "accept",
        "host",
        "user-agent",
    }


def test_redirecting_hostile_client_is_not_followed() -> None:
    class RedirectTransport(Transport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(
                302,
                headers={"Location": "https://wrong.invalid/secret"},
                request=request,
            )

    transport = RedirectTransport()
    http_client = httpx.AsyncClient(
        base_url="https://wrong.invalid",
        follow_redirects=True,
        transport=transport,
    )
    client = BuffAnonymousListingHttpClient(http_client)
    try:
        with pytest.raises(BuffAnonymousListingRequestError) as captured:
            asyncio.run(client.fetch_sell_order_payload(GOODS_ID))
    finally:
        asyncio.run(http_client.aclose())
    assert len(transport.requests) == 1
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_client_normalizes_external_goods_id_only() -> None:
    transport = Transport()
    http_client, client = _client(transport)
    try:
        asyncio.run(client.fetch_sell_order_payload(f"  {GOODS_ID}  "))
    finally:
        asyncio.run(http_client.aclose())
    assert transport.requests[0].url.params["goods_id"] == GOODS_ID


def test_client_borrows_http_client() -> None:
    transport = Transport()
    http_client, client = _client(transport)
    asyncio.run(client.fetch_sell_order_payload(GOODS_ID))
    assert transport.closed is False
    asyncio.run(http_client.aclose())
    assert transport.closed is True


def test_module_has_no_retry_or_forbidden_behavior() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "clients"
        / "buff_anonymous_listing_client.py"
    ).read_text(encoding="utf-8").casefold()
    for marker in (
        "retry",
        "sleep(",
        "page_size",
        "cookie=",
        "proxy=",
        "login",
        "purchase",
        "steamapis",
        "steamdt",
    ):
        assert marker not in source
