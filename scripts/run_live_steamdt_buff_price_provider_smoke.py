from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.services.price_provider import PriceQuote
from app.services.steamdt_buff_price_policy import SteamDTBuffPriceSelectionError
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.steamdt_market_data import SteamDTMarketDataClient
from scripts.steamdt_smoke_utils import parse_bool_env

RUN_GATE_ENV = "STEAMDT_RUN_BUFF_PROVIDER_SMOKE"
API_KEY_ENV = "STEAMDT_API_KEY"
MARKET_HASH_NAME_ENV = "STEAMDT_SMOKE_MARKET_HASH_NAME"
BASE_URL_ENV = "STEAMDT_BASE_URL"
DEFAULT_BASE_URL = "https://open.steamdt.com"


class SteamDTBuffProviderSmokeRuntime(Protocol):
    @property
    def client(self) -> SteamDTMarketDataClient:
        """Return the borrowed aggregate market-data client."""

    @property
    def request_count(self) -> int:
        """Return the number of attempted outbound SteamDT requests."""

    async def aclose(self) -> None:
        """Close every resource owned by the smoke runtime."""


class SteamDTBuffProviderSmokeRuntimeFactory(Protocol):
    def __call__(
        self,
        base_url: str,
        api_key: str,
    ) -> Awaitable[SteamDTBuffProviderSmokeRuntime]:
        """Create an owned one-attempt SteamDT provider runtime."""


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
) -> SteamDTBuffProviderSmokeRuntime:
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
    runtime_factory: SteamDTBuffProviderSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicitly enabled SteamDT BUFF PriceProvider request."""

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

    runtime: SteamDTBuffProviderSmokeRuntime | None = None
    request_count: int | None = 0
    success_lines: list[str] = []
    failure_reason: str | None = None
    try:
        create_runtime = runtime_factory or _create_http_smoke_runtime
        runtime = await create_runtime(base_url, api_key)
        provider = SteamDTBuffPriceProvider(runtime.client)
        quote = await provider.get_price(market_hash_name)
        if not _is_valid_quote(quote, market_hash_name=market_hash_name):
            failure_reason = "provider_result_invalid"
        request_count = _try_read_request_count(runtime)
        if request_count != 1:
            failure_reason = "request_count_invalid"
        elif failure_reason is None:
            success_lines = _success_lines(quote)
    except (MemoryError, asyncio.CancelledError):
        raise
    except SteamDTBuffPriceSelectionError as exc:
        failure_reason = exc.reason.value
        if runtime is not None:
            request_count = _try_read_request_count(runtime)
            if request_count is not None and request_count > 1:
                failure_reason = "request_count_invalid"
    except Exception:
        failure_reason = "price_provider_failed"
        if runtime is not None:
            request_count = _try_read_request_count(runtime)
            if request_count is not None and request_count > 1:
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

    if failure_reason is not None:
        _print_lines(
            printer,
            "live_smoke_executed: yes",
            "result: failed",
            f"reason: {failure_reason}",
            "SteamDT requests sent: "
            f"{'unavailable' if request_count is None else request_count}",
        )
        return 1

    _print_lines(
        printer,
        *success_lines,
        f"SteamDT requests sent: {request_count}",
    )
    return 0


def _read_request_count(runtime: SteamDTBuffProviderSmokeRuntime) -> int:
    request_count = runtime.request_count
    if type(request_count) is not int or request_count < 0:
        raise TypeError("SteamDT provider smoke runtime returned an invalid request count")
    return request_count


def _try_read_request_count(
    runtime: SteamDTBuffProviderSmokeRuntime,
) -> int | None:
    try:
        return _read_request_count(runtime)
    except MemoryError:
        raise
    except Exception:
        return None


def _is_valid_quote(quote: object, *, market_hash_name: str) -> bool:
    return (
        type(quote) is PriceQuote
        and quote.market_hash_name == market_hash_name
        and type(quote.price_cny) is Decimal
        and quote.price_cny.is_finite()
        and quote.price_cny > 0
        and quote.source == "steamdt:buff"
        and quote.raw is None
    )


def _success_lines(quote: PriceQuote) -> list[str]:
    return [
        "live_smoke_executed: yes",
        "result: success",
        "market_hash_name_requested: yes",
        "source: steamdt:buff",
        "price_quote_present: yes",
        f"price_cny: {quote.price_cny}",
    ]


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def main() -> None:
    """Run the explicitly enabled one-request SteamDT provider smoke."""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
