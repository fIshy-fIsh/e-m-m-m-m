from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.steamdt_smoke_utils import parse_bool_env

RUN_GATE_ENV = "BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE"
GOODS_ID_ENV = "BUFF_READONLY_SMOKE_GOODS_ID"
BASE_URL = "https://buff.163.com"
ENDPOINT_PATH = "/api/market/goods/sell_order"
USER_AGENT = "cs2-tradeup-readonly-schema-smoke/1.0"

_FAILURE_REASONS = frozenset(
    {
        "opt_in_disabled",
        "goods_id_missing",
        "goods_id_invalid",
        "runtime_failed",
        "request_failed",
        "anonymous_access_unavailable",
        "response_not_json",
        "response_schema_invalid",
        "items_missing",
        "no_items",
        "listing_id_missing",
        "price_invalid",
        "paintwear_invalid",
        "request_count_invalid",
        "close_failed",
    }
)
_SENSITIVE_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "device-id",
        "origin",
        "proxy-authorization",
        "referer",
        "x-csrftoken",
        "x-requested-with",
    }
)
_MISSING = object()


@dataclass(frozen=True, kw_only=True)
class BuffAnonymousSchemaRequestState:
    attempted: int
    dispatched: int
    budget_exceeded: bool


class BuffAnonymousSchemaSmokeRuntime(Protocol):
    @property
    def request_state(self) -> BuffAnonymousSchemaRequestState:
        """Return the current one-request budget state."""

    async def fetch_response(self) -> httpx.Response:
        """Fetch the fixed first-page anonymous sell-order response."""

    async def aclose(self) -> None:
        """Close every resource owned by the runtime."""


class BuffAnonymousSchemaSmokeRuntimeFactory(Protocol):
    def __call__(
        self,
        goods_id: str,
    ) -> Awaitable[BuffAnonymousSchemaSmokeRuntime]:
        """Create one owned runtime for the validated goods ID."""


class _RequestBudgetExceeded(RuntimeError):
    """A second request attempt exceeded the smoke budget."""


class _RequestContractViolation(RuntimeError):
    """An outbound request violated the fixed anonymous contract."""


class _InvalidJson(ValueError):
    """A JSON value violated the strict decoder contract."""


@dataclass(frozen=True, kw_only=True)
class _SchemaSummary:
    asset_id_present: bool
    paintseed_present: bool


@dataclass
class _HttpSmokeRuntime:
    _client: httpx.AsyncClient
    _goods_id: str
    _attempted: list[int]
    _dispatched: list[int]
    _budget_exceeded: list[bool]

    @property
    def request_state(self) -> BuffAnonymousSchemaRequestState:
        return BuffAnonymousSchemaRequestState(
            attempted=self._attempted[0],
            dispatched=self._dispatched[0],
            budget_exceeded=self._budget_exceeded[0],
        )

    async def fetch_response(self) -> httpx.Response:
        return await self._client.get(
            ENDPOINT_PATH,
            params=(
                ("game", "csgo"),
                ("goods_id", self._goods_id),
                ("page_num", "1"),
                ("sort_by", "default"),
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


async def _create_http_smoke_runtime(
    goods_id: str,
) -> BuffAnonymousSchemaSmokeRuntime:
    attempted = [0]
    dispatched = [0]
    budget_exceeded = [False]

    async def guard_request(request: httpx.Request) -> None:
        attempted[0] += 1
        if attempted[0] > 1:
            budget_exceeded[0] = True
            raise _RequestBudgetExceeded
        _validate_outbound_request(request, goods_id=goods_id)
        dispatched[0] += 1

    client = httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        event_hooks={"request": [guard_request]},
    )
    return _HttpSmokeRuntime(
        _client=client,
        _goods_id=goods_id,
        _attempted=attempted,
        _dispatched=dispatched,
        _budget_exceeded=budget_exceeded,
    )


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: BuffAnonymousSchemaSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicitly enabled anonymous BUFF schema request."""

    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_GATE_ENV):
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: opt_in_disabled",
            "BUFF requests sent: 0",
        )
        return 0

    goods_id_value = environ.get(GOODS_ID_ENV)
    if goods_id_value is None or (
        type(goods_id_value) is str and not goods_id_value.strip()
    ):
        return _print_guard_failure(printer, "goods_id_missing")
    if type(goods_id_value) is not str:
        return _print_guard_failure(printer, "goods_id_invalid")
    goods_id = goods_id_value.strip()

    runtime: BuffAnonymousSchemaSmokeRuntime | None = None
    request_state: BuffAnonymousSchemaRequestState | None = (
        BuffAnonymousSchemaRequestState(
            attempted=0,
            dispatched=0,
            budget_exceeded=False,
        )
    )
    failure_reason: str | None = None
    success_lines: list[str] = []
    try:
        create_runtime = runtime_factory or _create_http_smoke_runtime
        try:
            runtime = await create_runtime(goods_id)
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            failure_reason = "runtime_failed"

        if runtime is not None:
            try:
                response = await runtime.fetch_response()
                failure_reason, summary = _inspect_response(response)
                request_state = _try_read_request_state(runtime)
                if failure_reason is None:
                    if not _is_exact_success_state(request_state) or summary is None:
                        failure_reason = "request_count_invalid"
                    else:
                        success_lines = _success_lines(summary)
                elif _request_budget_was_exceeded(request_state):
                    failure_reason = "request_count_invalid"
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                failure_reason = "request_failed"
                request_state = _try_read_request_state(runtime)
                if _request_budget_was_exceeded(request_state):
                    failure_reason = "request_count_invalid"
    finally:
        if runtime is not None:
            try:
                await runtime.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                failure_reason = "close_failed"
                success_lines = []

    dispatched = None if request_state is None else request_state.dispatched
    if failure_reason is not None:
        _print_lines(
            printer,
            "live_smoke_executed: yes",
            "result: failed",
            f"reason: {failure_reason}",
            "BUFF requests sent: "
            f"{'unavailable' if dispatched is None else dispatched}",
        )
        return 1

    _print_lines(
        printer,
        *success_lines,
        f"BUFF requests sent: {dispatched}",
    )
    return 0


def _validate_outbound_request(request: httpx.Request, *, goods_id: str) -> None:
    expected_query = [
        ("game", "csgo"),
        ("goods_id", goods_id),
        ("page_num", "1"),
        ("sort_by", "default"),
    ]
    header_names = {name.casefold() for name in request.headers}
    if (
        request.method != "GET"
        or request.url.scheme != "https"
        or request.url.host != "buff.163.com"
        or request.url.port is not None
        or request.url.path != ENDPOINT_PATH
        or list(request.url.params.multi_items()) != expected_query
        or request.content != b""
        or request.headers.get("User-Agent") != USER_AGENT
        or request.headers.get("Accept") != "application/json"
        or _SENSITIVE_REQUEST_HEADERS.intersection(header_names)
        or request.url.username
        or request.url.password
    ):
        raise _RequestContractViolation


def _inspect_response(
    value: object,
) -> tuple[str | None, _SchemaSummary | None]:
    if type(value) is not httpx.Response:
        return "response_schema_invalid", None
    if not 200 <= value.status_code < 300:
        return "request_failed", None

    try:
        payload = json.loads(
            value.content,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_build_unique_object,
        )
    except MemoryError:
        raise
    except Exception:
        return "response_not_json", None

    if type(payload) is not dict:
        return "response_schema_invalid", None
    if payload.get("code") != "OK":
        return "anonymous_access_unavailable", None

    data = payload.get("data", _MISSING)
    if type(data) is not dict:
        return "response_schema_invalid", None
    items = data.get("items", _MISSING)
    if type(items) is not list:
        return "items_missing", None
    if not items:
        return "no_items", None

    item = items[0]
    if type(item) is not dict:
        return "response_schema_invalid", None
    if not _is_valid_listing_id(item.get("id", _MISSING)):
        return "listing_id_missing", None
    if _parse_positive_decimal(item.get("price", _MISSING)) is None:
        return "price_invalid", None

    asset_info = item.get("asset_info", _MISSING)
    if type(asset_info) is not dict:
        return "paintwear_invalid", None
    paintwear = _parse_decimal(asset_info.get("paintwear", _MISSING))
    if paintwear is None or not Decimal("0") <= paintwear <= Decimal("1"):
        return "paintwear_invalid", None

    return (
        None,
        _SchemaSummary(
            asset_id_present=(
                "assetid" in asset_info and asset_info["assetid"] is not None
            ),
            paintseed_present=(
                "paintseed" in asset_info and asset_info["paintseed"] is not None
            ),
        ),
    )


def _is_valid_listing_id(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _parse_positive_decimal(value: object) -> Decimal | None:
    parsed = _parse_decimal(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _parse_decimal(value: object) -> Decimal | None:
    try:
        if type(value) is str:
            if not value or value != value.strip():
                return None
            parsed = Decimal(value)
        elif type(value) is Decimal:
            parsed = value
        elif type(value) is int:
            parsed = Decimal(value)
        else:
            return None
        if not parsed.is_finite():
            return None
        return parsed
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _reject_json_constant(_value: str) -> object:
    raise _InvalidJson


def _build_unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJson
        result[key] = value
    return result


def _read_request_state(
    runtime: BuffAnonymousSchemaSmokeRuntime,
) -> BuffAnonymousSchemaRequestState:
    state = runtime.request_state
    if type(state) is not BuffAnonymousSchemaRequestState:
        raise TypeError("invalid anonymous BUFF schema smoke request state")
    if (
        type(state.attempted) is not int
        or state.attempted < 0
        or type(state.dispatched) is not int
        or state.dispatched < 0
        or state.dispatched > state.attempted
        or type(state.budget_exceeded) is not bool
    ):
        raise TypeError("invalid anonymous BUFF schema smoke request state")
    return state


def _try_read_request_state(
    runtime: BuffAnonymousSchemaSmokeRuntime,
) -> BuffAnonymousSchemaRequestState | None:
    try:
        return _read_request_state(runtime)
    except MemoryError:
        raise
    except Exception:
        return None


def _is_exact_success_state(
    state: BuffAnonymousSchemaRequestState | None,
) -> bool:
    return state == BuffAnonymousSchemaRequestState(
        attempted=1,
        dispatched=1,
        budget_exceeded=False,
    )


def _request_budget_was_exceeded(
    state: BuffAnonymousSchemaRequestState | None,
) -> bool:
    return state is not None and (
        state.budget_exceeded or state.attempted > 1 or state.dispatched > 1
    )


def _print_guard_failure(printer: Callable[[str], None], reason: str) -> int:
    _print_lines(
        printer,
        "live_smoke_executed: no",
        f"reason: {reason}",
        "BUFF requests sent: 0",
    )
    return 1


def _success_lines(summary: _SchemaSummary) -> list[str]:
    return [
        "live_smoke_executed: yes",
        "result: success",
        "anonymous_request: yes",
        "cookie_used: no",
        "login_used: no",
        "page_num: 1",
        "item_list_present: yes",
        "listing_item_present: yes",
        "listing_id_present: yes",
        "price_valid: yes",
        "paintwear_valid: yes",
        f"asset_id_present: {'yes' if summary.asset_id_present else 'no'}",
        f"paintseed_present: {'yes' if summary.paintseed_present else 'no'}",
    ]


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def main() -> None:
    """Run the explicitly enabled anonymous BUFF schema smoke."""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
