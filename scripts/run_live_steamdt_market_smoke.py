from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamdt_client import (
    SteamDTClientConfig,
    SteamDTHttpClient,
    SteamDTPlatformPrice,
)
from app.services.steamdt_market_data import (
    SteamDTMarketDataClient,
    get_steamdt_market_data,
)
from scripts.steamdt_smoke_utils import (
    parse_bool_env,
    safe_error_type,
    safe_external_text,
)

RUN_GATE_ENV = "STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE"
API_KEY_ENV = "STEAMDT_API_KEY"
MARKET_HASH_NAME_ENV = "STEAMDT_SMOKE_MARKET_HASH_NAME"
BASE_URL_ENV = "STEAMDT_BASE_URL"
DEFAULT_BASE_URL = "https://open.steamdt.com"


class SteamDTMarketSmokeRuntime(Protocol):
    @property
    def client(self) -> SteamDTMarketDataClient:
        """Return the borrowed aggregate market-data client."""

    @property
    def request_count(self) -> int:
        """Return the number of attempted outbound SteamDT requests."""

    async def aclose(self) -> None:
        """Close every resource owned by the smoke runtime."""


class SteamDTMarketSmokeRuntimeFactory(Protocol):
    def __call__(
        self,
        base_url: str,
        api_key: str,
    ) -> Awaitable[SteamDTMarketSmokeRuntime]:
        """Create an owned one-attempt SteamDT market runtime."""


@dataclass
class _HttpSmokeRuntime:
    _client: SteamDTHttpClient
    _request_counter: list[int]

    @property
    def client(self) -> SteamDTHttpClient:
        return self._client

    @property
    def request_count(self) -> int:
        return self._request_counter[0]

    async def aclose(self) -> None:
        await self._client.aclose()


async def _create_http_smoke_runtime(
    base_url: str,
    api_key: str,
) -> SteamDTMarketSmokeRuntime:
    request_counter = [0]

    async def count_request(_request: httpx.Request) -> None:
        request_counter[0] += 1

    http_client = httpx.AsyncClient(
        base_url=base_url,
        timeout=10.0,
        follow_redirects=False,
        event_hooks={"request": [count_request]},
    )
    try:
        client = SteamDTHttpClient(
            SteamDTClientConfig(
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=10.0,
                max_retries=0,
                dry_run=False,
            ),
            http_client=http_client,
        )
    except BaseException:
        await http_client.aclose()
        raise
    return _HttpSmokeRuntime(_client=client, _request_counter=request_counter)


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: SteamDTMarketSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicitly enabled SteamDT aggregate market-data request."""

    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_GATE_ENV):
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: opt_in_disabled",
            "SteamDT requests sent: 0",
        )
        return 0

    api_key_value = environ.get(API_KEY_ENV)
    if api_key_value is None or not api_key_value.strip():
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: api_key_missing",
            "SteamDT requests sent: 0",
        )
        return 1
    api_key = api_key_value.strip()

    market_hash_name_value = environ.get(MARKET_HASH_NAME_ENV)
    if market_hash_name_value is None or not market_hash_name_value.strip():
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: market_hash_name_missing",
            "SteamDT requests sent: 0",
        )
        return 1
    market_hash_name = market_hash_name_value.strip()
    base_url = environ.get(BASE_URL_ENV, DEFAULT_BASE_URL)

    runtime: SteamDTMarketSmokeRuntime | None = None
    request_count: int | None = 0
    result_lines: list[str] = []
    failure_reason: str | None = None
    failure_type: str | None = None
    try:
        create_runtime = runtime_factory or _create_http_smoke_runtime
        runtime = await create_runtime(base_url, api_key)
        result = await get_steamdt_market_data(
            client=runtime.client,
            market_hash_name=market_hash_name,
        )
        request_count = _read_request_count(runtime)
        if request_count != 1:
            failure_reason = "request_count_invalid"
        elif not result.quotes:
            failure_reason = "no_platform_records"
        else:
            result_lines = _success_lines(result.quotes, api_key=api_key)
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception as exc:
        failure_reason = "market_data_failed"
        failure_type = safe_error_type(exc)
        if runtime is not None:
            request_count = _try_read_request_count(runtime)
    finally:
        if runtime is not None:
            try:
                await runtime.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception as exc:
                failure_reason = "close_failed"
                failure_type = safe_error_type(exc)
                result_lines = []

    if failure_reason is not None:
        lines = [
            "live_smoke_executed: yes",
            "result: failed",
            f"reason: {failure_reason}",
        ]
        if failure_type is not None:
            lines.append(f"error_type: {failure_type}")
        lines.append(
            "SteamDT requests sent: "
            f"{'unavailable' if request_count is None else request_count}"
        )
        _print_lines(printer, *lines)
        return 1

    _print_lines(
        printer,
        *result_lines,
        f"SteamDT requests sent: {request_count}",
    )
    return 0


def _read_request_count(runtime: SteamDTMarketSmokeRuntime) -> int:
    request_count = runtime.request_count
    if type(request_count) is not int or request_count < 0:
        raise TypeError("SteamDT market smoke runtime returned an invalid request count")
    return request_count


def _try_read_request_count(runtime: SteamDTMarketSmokeRuntime) -> int | None:
    try:
        return _read_request_count(runtime)
    except Exception:
        return None


def _success_lines(
    quotes: tuple[SteamDTPlatformPrice, ...],
    *,
    api_key: str,
) -> list[str]:
    lines = [
        "live_smoke_executed: yes",
        "result: success",
        "market_hash_name_requested: yes",
        f"platform_count: {len(quotes)}",
    ]
    for quote in quotes:
        if type(quote) is not SteamDTPlatformPrice:
            raise TypeError("SteamDT market smoke received an invalid quote")
        lines.extend(
            (
                f"platform: {safe_external_text(quote.platform, api_key=api_key)}",
                "platform_item_id_present: "
                f"{_yes_no(quote.platform_item_id is not None)}",
                f"sell_price_cny: {_value_or_missing(quote.sell_price_cny)}",
                f"sell_count: {_value_or_missing(quote.sell_count)}",
                f"bidding_price_cny: {_value_or_missing(quote.bidding_price_cny)}",
                f"bidding_count: {_value_or_missing(quote.bidding_count)}",
                f"update_time_present: {_yes_no(quote.update_time is not None)}",
            )
        )
    return lines


def _value_or_missing(value: object | None) -> str:
    return "missing" if value is None else str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def main() -> None:
    """Run the explicitly enabled one-request SteamDT market smoke."""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
