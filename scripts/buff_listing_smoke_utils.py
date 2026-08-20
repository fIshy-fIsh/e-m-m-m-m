from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.clients.buff_anonymous_listing_client import (
    BUFF_ANONYMOUS_BASE_URL,
    BUFF_ANONYMOUS_USER_AGENT,
    BuffAnonymousListingHttpClient,
    BuffAnonymousListingPayloadClient,
    validate_buff_anonymous_listing_request,
)


@dataclass(frozen=True, kw_only=True)
class BuffListingSmokeRequestState:
    attempted: int
    dispatched: int
    budget_exceeded: bool


class BuffListingSmokeRuntime(Protocol):
    @property
    def client(self) -> BuffAnonymousListingPayloadClient: ...

    @property
    def request_state(self) -> BuffListingSmokeRequestState: ...

    async def aclose(self) -> None: ...


class BuffListingSmokeRuntimeFactory(Protocol):
    def __call__(self, goods_id: str) -> Awaitable[BuffListingSmokeRuntime]: ...


class _RequestBudgetExceeded(RuntimeError):
    pass


@dataclass
class _HttpSmokeRuntime:
    _http_client: httpx.AsyncClient
    _client: BuffAnonymousListingHttpClient
    _goods_id: str
    _attempted: list[int]
    _dispatched: list[int]
    _budget_exceeded: list[bool]

    @property
    def client(self) -> BuffAnonymousListingHttpClient:
        return self._client

    @property
    def request_state(self) -> BuffListingSmokeRequestState:
        return BuffListingSmokeRequestState(
            attempted=self._attempted[0],
            dispatched=self._dispatched[0],
            budget_exceeded=self._budget_exceeded[0],
        )

    async def fetch_response(self) -> httpx.Response:
        await self._client.fetch_sell_order_payload(self._goods_id)
        return httpx.Response(200)

    async def aclose(self) -> None:
        await self._http_client.aclose()


async def create_buff_listing_smoke_runtime(
    goods_id: str,
) -> BuffListingSmokeRuntime:
    attempted = [0]
    dispatched = [0]
    exceeded = [False]

    async def guard(request: httpx.Request) -> None:
        attempted[0] += 1
        if attempted[0] > 1:
            exceeded[0] = True
            raise _RequestBudgetExceeded
        validate_buff_anonymous_listing_request(request, goods_id=goods_id)
        dispatched[0] += 1

    http_client = httpx.AsyncClient(
        base_url=BUFF_ANONYMOUS_BASE_URL,
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
        headers={
            "Accept": "application/json",
            "User-Agent": BUFF_ANONYMOUS_USER_AGENT,
        },
        event_hooks={"request": [guard]},
    )
    try:
        client = BuffAnonymousListingHttpClient(http_client)
    except BaseException as exc:
        try:
            await http_client.aclose()
        except Exception:
            raise exc from None
        raise
    return _HttpSmokeRuntime(
        _http_client=http_client,
        _client=client,
        _goods_id=goods_id,
        _attempted=attempted,
        _dispatched=dispatched,
        _budget_exceeded=exceeded,
    )


def read_request_state(runtime: BuffListingSmokeRuntime) -> BuffListingSmokeRequestState:
    state = runtime.request_state
    if type(state) is not BuffListingSmokeRequestState:
        raise TypeError("invalid BUFF listing smoke request state")
    if (
        type(state.attempted) is not int
        or state.attempted < 0
        or type(state.dispatched) is not int
        or state.dispatched < 0
        or state.dispatched > state.attempted
        or type(state.budget_exceeded) is not bool
    ):
        raise TypeError("invalid BUFF listing smoke request state")
    return state


def try_read_request_state(
    runtime: BuffListingSmokeRuntime,
) -> BuffListingSmokeRequestState | None:
    try:
        return read_request_state(runtime)
    except MemoryError:
        raise
    except Exception:
        return None


def is_exact_success_state(state: BuffListingSmokeRequestState | None) -> bool:
    return state == BuffListingSmokeRequestState(
        attempted=1,
        dispatched=1,
        budget_exceeded=False,
    )


def budget_was_exceeded(state: BuffListingSmokeRequestState | None) -> bool:
    return state is not None and (
        state.budget_exceeded or state.attempted > 1 or state.dispatched > 1
    )


def print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)
