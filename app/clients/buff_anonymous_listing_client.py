from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

BUFF_ANONYMOUS_BASE_URL = "https://buff.163.com"
BUFF_ANONYMOUS_SELL_ORDER_PATH = "/api/market/goods/sell_order"
BUFF_ANONYMOUS_USER_AGENT = "cs2-tradeup-readonly-schema-smoke/1.0"
_FIXED_ERROR = "anonymous BUFF listing request failed"
_ALLOWED_HEADER_NAMES = frozenset({"accept", "host", "user-agent"})

__all__ = (
    "BUFF_ANONYMOUS_BASE_URL",
    "BUFF_ANONYMOUS_SELL_ORDER_PATH",
    "BUFF_ANONYMOUS_USER_AGENT",
    "BuffAnonymousListingRequestError",
    "BuffAnonymousListingPayloadClient",
    "BuffAnonymousListingHttpClient",
    "validate_buff_anonymous_listing_request",
)


class BuffAnonymousListingRequestError(RuntimeError):
    """An anonymous BUFF request failed without exposing external details."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR)


class BuffAnonymousListingPayloadClient(Protocol):
    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        """Fetch one first-page anonymous sell-order payload."""


class BuffAnonymousListingHttpClient:
    """Borrowed HTTPX client for one anonymous sell-order request per call."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        if not hasattr(http_client, "send"):
            raise TypeError("http_client must provide send")
        self._http_client = http_client

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        canonical_goods_id = _normalize_provider_goods_id(goods_id)
        request = httpx.Request(
            "GET",
            f"{BUFF_ANONYMOUS_BASE_URL}{BUFF_ANONYMOUS_SELL_ORDER_PATH}",
            params=(
                ("game", "csgo"),
                ("goods_id", canonical_goods_id),
                ("page_num", "1"),
                ("sort_by", "default"),
            ),
            headers=(
                ("Accept", "application/json"),
                ("Host", "buff.163.com"),
                ("User-Agent", BUFF_ANONYMOUS_USER_AGENT),
            ),
            content=b"",
        )
        validate_buff_anonymous_listing_request(
            request,
            goods_id=canonical_goods_id,
        )

        failed = False
        response: httpx.Response | None = None
        try:
            response = await self._http_client.send(
                request,
                auth=None,
                follow_redirects=False,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            failed = True
        if failed or response is None or not 200 <= response.status_code < 300:
            raise BuffAnonymousListingRequestError
        return bytes(response.content)


def validate_buff_anonymous_listing_request(
    request: httpx.Request,
    *,
    goods_id: str,
) -> None:
    """Fail closed unless one request matches the empirical read-only contract."""

    canonical_goods_id = _validate_exact_goods_id(goods_id)
    expected_query = [
        ("game", "csgo"),
        ("goods_id", canonical_goods_id),
        ("page_num", "1"),
        ("sort_by", "default"),
    ]
    names = [name.casefold() for name in request.headers]
    if (
        request.method != "GET"
        or request.url.scheme != "https"
        or request.url.host != "buff.163.com"
        or request.url.port is not None
        or request.url.path != BUFF_ANONYMOUS_SELL_ORDER_PATH
        or list(request.url.params.multi_items()) != expected_query
        or request.content != b""
        or request.headers.get("Host") != "buff.163.com"
        or request.headers.get("User-Agent") != BUFF_ANONYMOUS_USER_AGENT
        or request.headers.get("Accept") != "application/json"
        or set(names) != _ALLOWED_HEADER_NAMES
        or len(names) != len(_ALLOWED_HEADER_NAMES)
        or request.url.username
        or request.url.password
    ):
        raise BuffAnonymousListingRequestError


def _normalize_provider_goods_id(value: object) -> str:
    if type(value) is not str:
        raise BuffAnonymousListingRequestError
    canonical = value.strip()
    if not canonical:
        raise BuffAnonymousListingRequestError
    return canonical


def _validate_exact_goods_id(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise BuffAnonymousListingRequestError
    return value