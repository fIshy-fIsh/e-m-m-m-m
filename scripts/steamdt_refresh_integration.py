from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Never, Protocol

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.config import Settings
from app.services.price_cache import InMemoryPriceCache, PriceCachePolicy
from app.services.steamdt_cached_price_resolver import (
    SteamDTCachedPriceResolution,
    SteamDTCachedPriceResolver,
)
from app.services.steamdt_price_refresh_service import (
    SteamDTFetchedPriceSnapshot,
    SteamDTPriceRefreshResult,
    SteamDTPriceRefreshService,
)
from app.services.steamdt_price_snapshot_source import (
    SteamDTSinglePriceCandidateClient,
    SteamDTSinglePriceSnapshotSource,
)
from app.services.steamdt_rate_limiter_factory import (
    SteamDTClientRuntime,
    build_steamdt_client_config,
    create_steamdt_client_runtime,
)
from app.services.steamdt_refresh_executor import (
    SteamDTRefreshExecutionReport,
    SteamDTRefreshExecutor,
)
from app.services.steamdt_refresh_planner import (
    SteamDTRefreshPlan,
    SteamDTRefreshPlanner,
    SteamDTRefreshPlannerValidationError,
)
from scripts.steamdt_smoke_utils import (
    parse_bool_env,
    safe_error_type,
    safe_external_text,
)

RUN_GATE_ENV = "STEAMDT_RUN_REFRESH_INTEGRATION"
DEFAULT_CHUNK_SIZE = 5
DEFAULT_MAX_CONCURRENCY = 2
INTEGRATION_POLICY = PriceCachePolicy(fresh_ttl=timedelta(minutes=5))
_FAKE_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class SteamDTRefreshIntegrationRuntime(Protocol):
    client: SteamDTSinglePriceCandidateClient

    @property
    def request_count(self) -> int:
        """Return attempted outbound SteamDT requests."""

    async def aclose(self) -> None:
        """Close every resource owned by the integration runtime."""


class SteamDTRefreshIntegrationRuntimeFactory(Protocol):
    async def __call__(
        self,
        environ: Mapping[str, str],
    ) -> SteamDTRefreshIntegrationRuntime:
        """Create an owned live SteamDT runtime after all gates pass."""


class SteamDTRefreshSnapshotSource(Protocol):
    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        """Fetch one selector-before snapshot."""


class SteamDTRefreshSnapshotSourceFactory(Protocol):
    def __call__(self) -> SteamDTRefreshSnapshotSource:
        """Create a borrowed fake snapshot source."""


class SteamDTRefreshResolverFactory(Protocol):
    def __call__(
        self,
        cache: InMemoryPriceCache,
    ) -> SteamDTCachedPriceResolver:
        """Create a resolver over the command's shared cache."""


@dataclass(frozen=True)
class SteamDTRefreshIntegrationOptions:
    mode: str
    items: tuple[str, ...]
    chunk_size: int
    max_concurrency: int


@dataclass
class _ComposedLiveRuntime:
    runtime: SteamDTClientRuntime
    _request_counter: list[int]

    @property
    def client(self) -> SteamDTSinglePriceCandidateClient:
        return self.runtime.client

    @property
    def request_count(self) -> int:
        return self._request_counter[0]

    async def aclose(self) -> None:
        await self.runtime.aclose()


class _DeterministicFakeSnapshotSource:
    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        candidates = (
            SteamDTPlatformPrice(
                platform="synthetic-alpha",
                platform_item_id="fake-alpha",
                sell_price_cny=Decimal("101.25"),
                sell_count=25,
                bidding_price_cny=Decimal("98.10"),
                bidding_count=12,
                update_time="synthetic-fixed",
            ),
            SteamDTPlatformPrice(
                platform="synthetic-beta",
                platform_item_id="fake-beta",
                sell_price_cny=Decimal("99.50"),
                sell_count=18,
                bidding_price_cny=Decimal("97.40"),
                bidding_count=9,
                update_time="synthetic-fixed",
            ),
        )
        return SteamDTFetchedPriceSnapshot(
            market_hash_name=market_hash_name,
            source="steamdt",
            candidates=candidates,
            observed_at=_FAKE_NOW,
        )


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise SteamDTRefreshIntegrationCliError from None


class SteamDTRefreshIntegrationCliError(ValueError):
    """The manual command arguments violated the public CLI contract."""


async def async_main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    live_runtime_factory: SteamDTRefreshIntegrationRuntimeFactory | None = None,
    fake_source_factory: SteamDTRefreshSnapshotSourceFactory | None = None,
    resolver_factory: SteamDTRefreshResolverFactory | None = None,
) -> int:
    """Run the manual planner-to-cache integration command."""

    try:
        options = parse_options(argv)
        plan = SteamDTRefreshPlanner(chunk_size=options.chunk_size).plan(options.items)
    except (SteamDTRefreshIntegrationCliError, SteamDTRefreshPlannerValidationError) as exc:
        printer(
            "SteamDT refresh integration validation failed: "
            f"{safe_error_type(exc)}"
        )
        printer("SteamDT requests sent: 0")
        printer("Redis used: no")
        return 2

    environ = os.environ if environ is None else environ
    api_key: str | None = None
    runtime: SteamDTRefreshIntegrationRuntime | None = None
    request_count: int | None = 0 if options.mode == "fake" else None

    if options.mode == "live":
        if not parse_bool_env(environ, RUN_GATE_ENV):
            printer(
                "SteamDT refresh integration live gate failed: "
                f"{RUN_GATE_ENV} is not true."
            )
            printer("SteamDT requests sent: 0")
            printer("Redis used: no")
            return 2
        api_key = environ.get("STEAMDT_API_KEY")
        if api_key is None or not api_key.strip():
            printer("SteamDT refresh integration validation failed: missing API key")
            printer("SteamDT requests sent: 0")
            printer("Redis used: no")
            return 2
        api_key = api_key.strip()

    operation_error: Exception | None = None
    close_error: Exception | None = None
    cancellation: asyncio.CancelledError | None = None
    summary_lines: list[str] = []
    report: SteamDTRefreshExecutionReport | None = None
    try:
        if options.mode == "live":
            create_runtime = live_runtime_factory or _create_live_runtime
            runtime = await create_runtime(environ)
            source: SteamDTRefreshSnapshotSource = SteamDTSinglePriceSnapshotSource(
                runtime.client
            )
            cache = InMemoryPriceCache()
        else:
            create_source = fake_source_factory or _DeterministicFakeSnapshotSource
            source = create_source()
            cache = InMemoryPriceCache(clock=lambda: _FAKE_NOW)

        refresh_service = SteamDTPriceRefreshService(source, cache)
        executor = SteamDTRefreshExecutor(
            refresh_service,
            max_concurrency=options.max_concurrency,
        )
        report = await executor.execute(plan, INTEGRATION_POLICY)

        create_resolver = resolver_factory or SteamDTCachedPriceResolver
        resolver = create_resolver(cache)
        resolutions = tuple(
            [
                await resolver.resolve(
                    item.market_hash_name,
                    selection_config=SteamDTPriceSelectionConfig(),
                )
                for item in plan.ordered_unique_items
            ]
        )
        if runtime is not None:
            request_count = _read_request_count(runtime)
        summary_lines = _build_summary_lines(
            options=options,
            plan=plan,
            report=report,
            resolutions=resolutions,
            request_count=request_count,
            api_key=api_key,
        )
    except asyncio.CancelledError as exc:
        cancellation = exc
    except Exception as exc:
        operation_error = exc
        if runtime is not None:
            try:
                request_count = _read_request_count(runtime)
            except Exception:
                request_count = None
    finally:
        if runtime is not None:
            try:
                await runtime.aclose()
            except asyncio.CancelledError as exc:
                if cancellation is None:
                    cancellation = exc
            except Exception as exc:
                close_error = exc

    if cancellation is not None:
        raise cancellation

    for line in summary_lines:
        printer(line)
    if operation_error is not None:
        printer(
            "SteamDT refresh integration failed: "
            f"{safe_error_type(operation_error)}"
        )
    if close_error is not None:
        printer(
            "SteamDT refresh integration close failed: "
            f"{safe_error_type(close_error)}"
        )
    if not summary_lines:
        printer(
            "SteamDT requests sent: "
            f"{'unavailable' if request_count is None else request_count}"
        )
        printer("Redis used: no")

    failed = (
        operation_error is not None
        or close_error is not None
        or report is None
        or report.failure_count > 0
    )
    return 1 if failed else 0


def parse_options(argv: Sequence[str] | None = None) -> SteamDTRefreshIntegrationOptions:
    """Parse arguments without normalizing market hash names."""

    parser = _ArgumentParser(
        prog="steamdt_refresh_integration",
        description="Run the manual SteamDT refresh integration chain.",
    )
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument("--item", action="append", dest="items")
    parser.add_argument(
        "--chunk-size",
        type=_positive_int,
        default=DEFAULT_CHUNK_SIZE,
    )
    parser.add_argument(
        "--max-concurrency",
        type=_positive_int,
        default=DEFAULT_MAX_CONCURRENCY,
    )
    try:
        namespace = parser.parse_args(argv)
    except SystemExit:
        raise
    if not namespace.items:
        raise SteamDTRefreshIntegrationCliError
    return SteamDTRefreshIntegrationOptions(
        mode=namespace.mode,
        items=tuple(namespace.items),
        chunk_size=namespace.chunk_size,
        max_concurrency=namespace.max_concurrency,
    )


def _positive_int(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError from exc
    if value <= 0:
        raise argparse.ArgumentTypeError
    return value


async def _create_live_runtime(
    environ: Mapping[str, str],
) -> SteamDTRefreshIntegrationRuntime:
    settings = _build_live_settings(environ)
    config = build_steamdt_client_config(settings)
    request_counter = [0]

    async def count_request(_request: httpx.Request) -> None:
        request_counter[0] += 1

    http_client = httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        follow_redirects=False,
        event_hooks={"request": [count_request]},
    )
    try:
        runtime = await create_steamdt_client_runtime(
            settings,
            http_client=http_client,
        )
    except BaseException:
        await http_client.aclose()
        raise
    return _ComposedLiveRuntime(
        runtime=runtime,
        _request_counter=request_counter,
    )


def _build_live_settings(environ: Mapping[str, str]) -> Settings:
    api_key = environ.get("STEAMDT_API_KEY", "").strip()
    return Settings(
        _env_file=None,
        database_url="",
        redis_url="",
        bymykel_base_url="",
        steamdt_base_url=environ.get(
            "STEAMDT_BASE_URL",
            "https://open.steamdt.com",
        ),
        steamdt_api_key=api_key,
        steamdt_dry_run=False,
        steamdt_rate_limit_per_minute=environ.get(
            "STEAMDT_RATE_LIMIT_PER_MINUTE",
            "60",
        ),
        steamdt_rate_limit_price_single_per_minute=environ.get(
            "STEAMDT_RATE_LIMIT_PRICE_SINGLE_PER_MINUTE",
            "60",
        ),
        steamdt_rate_limit_price_batch_per_minute=environ.get(
            "STEAMDT_RATE_LIMIT_PRICE_BATCH_PER_MINUTE",
            "1",
        ),
        steamdt_rate_limit_price_avg_per_minute=environ.get(
            "STEAMDT_RATE_LIMIT_PRICE_AVG_PER_MINUTE",
            "10",
        ),
        steamdt_rate_limit_base_per_day=environ.get(
            "STEAMDT_RATE_LIMIT_BASE_PER_DAY",
            "1",
        ),
        steamdt_rate_limit_kline_per_minute=environ.get(
            "STEAMDT_RATE_LIMIT_KLINE_PER_MINUTE",
            "120",
        ),
        steamdt_rate_limit_wear_per_hour=environ.get(
            "STEAMDT_RATE_LIMIT_WEAR_PER_HOUR",
            "36000",
        ),
        steamdt_rate_limit_price_batch_safety_buffer_seconds=environ.get(
            "STEAMDT_RATE_LIMIT_PRICE_BATCH_SAFETY_BUFFER_SECONDS",
            "5",
        ),
        steamdt_rate_limit_backend="inmemory",
        steamdt_price_cache_backend="inmemory",
    )


def _read_request_count(runtime: SteamDTRefreshIntegrationRuntime) -> int:
    request_count = runtime.request_count
    if type(request_count) is not int or request_count < 0:
        raise TypeError("integration runtime returned an invalid request count")
    return request_count


def _build_summary_lines(
    *,
    options: SteamDTRefreshIntegrationOptions,
    plan: SteamDTRefreshPlan,
    report: SteamDTRefreshExecutionReport,
    resolutions: tuple[SteamDTCachedPriceResolution, ...],
    request_count: int | None,
    api_key: str | None,
) -> list[str]:
    if len(resolutions) != len(report.item_results):
        raise RuntimeError("resolution count did not match execution report")
    selected_quotes = sum(resolution.quote is not None for resolution in resolutions)
    lines = [
        "Integration command: steamdt_refresh_integration",
        f"Mode: {options.mode}",
        f"Synthetic data: {'yes' if options.mode == 'fake' else 'no'}",
        f"Input items: {plan.input_count}",
        f"Unique items: {plan.unique_count}",
        f"Duplicates removed: {plan.duplicate_count}",
        f"Chunks: {report.chunk_count}",
        f"Chunk size: {plan.chunk_size}",
        f"Max concurrency: {report.max_concurrency}",
        f"Refresh success: {report.success_count}",
        f"Refresh failure: {report.failure_count}",
        f"No candidates: {report.no_candidates_count}",
        f"Selected quotes: {selected_quotes}",
    ]
    for result, resolution in zip(report.item_results, resolutions, strict=True):
        refresh = result.refresh_result
        quote = resolution.quote
        selection = resolution.selection_result
        selected_platform = None if selection is None else selection.selected_platform
        lines.extend(
            [
                f"Item {result.unique_item_index}:",
                "  Canonical item: "
                f"{safe_external_text(result.market_hash_name, api_key=api_key)}",
                f"  Occurrence count: {result.item.occurrence_count}",
                f"  Chunk index: {result.chunk_index}",
                f"  Execution status: {result.status.value}",
                "  Refresh status: "
                f"{None if refresh is None else refresh.status.value}",
                "  Cache write outcome: "
                f"{_cache_write_value(refresh)}",
                f"  Cache lookup hit: {resolution.lookup.hit}",
                "  Cache state: "
                f"{None if resolution.lookup.state is None else resolution.lookup.state.value}",
                f"  Resolution status: {resolution.status.value}",
                "  Selected platform: "
                f"{safe_external_text(selected_platform, api_key=api_key)}",
                f"  Selected price: {None if quote is None else quote.price_cny}",
                f"  needs_refresh: {resolution.lookup.needs_refresh}",
                "  Safe error type: "
                f"{None if result.error is None else safe_error_type(result.error)}",
            ]
        )
    lines.extend(
        [
            "SteamDT requests sent: "
            f"{'unavailable' if request_count is None else request_count}",
            "Redis used: no",
        ]
    )
    return lines


def _cache_write_value(
    refresh: SteamDTPriceRefreshResult | None,
) -> str | None:
    if refresh is None or refresh.write_result is None:
        return None
    return refresh.write_result.value


def main() -> None:
    """Run the manual SteamDT refresh integration command."""

    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
