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
        "auth=",
        "proxy=",
        "login",
        "purchase",
        "steamapis",
        "steamdt",
    ):
        assert marker not in source
