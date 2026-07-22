import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.price_cache import InMemoryPriceCache, PriceCachePolicy
from app.services.steamdt_cached_price_resolver import SteamDTCachedPriceResolver
from app.services.steamdt_price_refresh_service import SteamDTPriceRefreshService
from app.services.steamdt_price_snapshot_source import (
    SteamDTSinglePriceCandidateClient,
    SteamDTSinglePriceSnapshotSource,
)

if __package__:
    from .steamdt_smoke_utils import parse_bool_env, print_guard_exit, redact_message
else:
    from steamdt_smoke_utils import parse_bool_env, print_guard_exit, redact_message

RUN_GATE_ENV = "STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE"
SMOKE_POLICY = PriceCachePolicy(fresh_ttl=timedelta(minutes=5))


class SteamDTPriceSnapshotSmokeRuntime(Protocol):
    client: SteamDTSinglePriceCandidateClient

    @property
    def request_count(self) -> int:
        """Return the number of attempted outbound SteamDT requests."""

    async def aclose(self) -> None:
        """Close every resource owned by the smoke runtime."""


class SteamDTPriceSnapshotSmokeRuntimeFactory(Protocol):
    def __call__(
        self,
        base_url: str,
        api_key: str,
    ) -> Awaitable[SteamDTPriceSnapshotSmokeRuntime]:
        """Create an owned one-attempt SteamDT smoke runtime."""


@dataclass
class _HttpSmokeRuntime:
    client: SteamDTHttpClient
    _request_counter: list[int]

    @property
    def request_count(self) -> int:
        return self._request_counter[0]

    async def aclose(self) -> None:
        await self.client.aclose()


async def _create_http_smoke_runtime(
    base_url: str,
    api_key: str,
) -> SteamDTPriceSnapshotSmokeRuntime:
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
    return _HttpSmokeRuntime(client=client, _request_counter=request_counter)


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: SteamDTPriceSnapshotSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicit read-only snapshot refresh and cached resolution."""

    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_GATE_ENV):
        print_guard_exit(
            printer,
            f"SteamDT price snapshot smoke skipped: {RUN_GATE_ENV} is not true.",
        )
        printer("SteamDT requests sent: 0")
        return 0

    api_key = environ.get("STEAMDT_API_KEY")
    if not api_key:
        print_guard_exit(
            printer,
            "SteamDT price snapshot smoke skipped: STEAMDT_API_KEY is missing.",
        )
        printer("SteamDT requests sent: 0")
        return 0

    market_hash_name = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAME")
    if market_hash_name is None or not market_hash_name.strip():
        print_guard_exit(
            printer,
            "SteamDT price snapshot smoke skipped: "
            "STEAMDT_SMOKE_MARKET_HASH_NAME is missing.",
        )
        printer("SteamDT requests sent: 0")
        return 0
    market_hash_name = market_hash_name.strip()
    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")

    runtime: SteamDTPriceSnapshotSmokeRuntime | None = None
    operation_error: Exception | None = None
    close_error: Exception | None = None
    request_count: int | None = 0
    request_count_read = False
    summary_lines: list[str] = []
    try:
        create_runtime = runtime_factory or _create_http_smoke_runtime
        runtime = await create_runtime(base_url, api_key)
        source = SteamDTSinglePriceSnapshotSource(runtime.client)
        cache = InMemoryPriceCache()
        refresh_service = SteamDTPriceRefreshService(source, cache)
        resolver = SteamDTCachedPriceResolver(cache)

        refresh_result = await refresh_service.refresh_one(
            market_hash_name,
            SMOKE_POLICY,
        )
        resolution = await resolver.resolve(
            market_hash_name,
            selection_config=SteamDTPriceSelectionConfig(),
        )
        request_count = _read_request_count(runtime)
        request_count_read = True
        if request_count != 1:
            raise RuntimeError("snapshot smoke must attempt exactly one SteamDT request")

        selection_result = resolution.selection_result
        quote = resolution.quote
        selected_platform = (
            None if selection_result is None else selection_result.selected_platform
        )
        summary_lines = [
            "smoke script: steamdt_price_snapshot_smoke",
            f"item: {_safe_external_text(refresh_result.key.market_hash_name, api_key=api_key)}",
            f"candidate count: {refresh_result.candidate_count}",
            f"observed_at: {refresh_result.observed_at.isoformat()}",
            "cache write result: "
            f"{None if refresh_result.write_result is None else refresh_result.write_result.value}",
            "cache state: "
            f"{None if resolution.lookup.state is None else resolution.lookup.state.value}",
            "selected platform: "
            f"{_safe_external_text(selected_platform, api_key=api_key)}",
            f"selected price: {None if quote is None else quote.price_cny}",
            f"needs_refresh: {resolution.lookup.needs_refresh}",
            f"refresh status: {refresh_result.status.value}",
            f"resolution status: {resolution.status.value}",
        ]
    except Exception as exc:
        operation_error = exc
        if runtime is not None and not request_count_read:
            try:
                request_count = _read_request_count(runtime)
            except Exception:
                request_count = None
    finally:
        if runtime is not None:
            try:
                await runtime.aclose()
            except Exception as exc:
                close_error = exc

    for line in summary_lines:
        printer(line)
    if operation_error is not None:
        printer(
            "SteamDT price snapshot smoke failed: "
            f"{_safe_error_type(operation_error)}"
        )
    if close_error is not None:
        printer(
            "SteamDT price snapshot smoke close failed: "
            f"{_safe_error_type(close_error)}"
        )
    printer(
        "SteamDT requests sent: "
        f"{'unavailable' if request_count is None else request_count}"
    )
    return 1 if operation_error is not None or close_error is not None else 0


def _read_request_count(runtime: SteamDTPriceSnapshotSmokeRuntime) -> int:
    request_count = runtime.request_count
    if type(request_count) is not int or request_count < 0:
        raise TypeError("snapshot smoke runtime returned an invalid request count")
    return request_count


def _safe_external_text(value: str | None, *, api_key: str) -> str:
    if value is None:
        return "None"
    return json.dumps(redact_message(value, api_key=api_key))


def _safe_error_type(error: Exception) -> str:
    name = type(error).__name__
    if not name.isascii() or not name.isidentifier():
        return "InternalError"
    return name


def main() -> None:
    """Run the explicitly enabled one-item read-only SteamDT snapshot smoke."""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
