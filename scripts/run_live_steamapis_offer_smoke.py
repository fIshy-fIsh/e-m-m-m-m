from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Never

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamapis_websocket_client import (
    SteamApisWebSocketClient,
    SteamApisWebSocketConfig,
)
from app.services.steamapis_listing import SteamApisListingEventType
from app.services.steamapis_offer_pool import SteamApisOfferPool
from app.services.steamapis_offer_session import run_steamapis_offer_session

RUN_GATE_ENV = "ENABLE_LIVE_STEAMAPIS_SMOKE"
API_KEY_ENV = "STEAMAPIS_API_KEY"
DEFAULT_DURATION_SECONDS = 15
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 60
SMOKE_POOL_MAX_SIZE = 5_000
SMOKE_POOL_TTL = timedelta(minutes=10)


class _InvalidArguments(Exception):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        raise _InvalidArguments from None


def _duration(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError from None
    if str(parsed) != value.strip() or not (
        MIN_DURATION_SECONDS <= parsed <= MAX_DURATION_SECONDS
    ):
        raise argparse.ArgumentTypeError from None
    return parsed


def _parse_arguments(argv: Sequence[str] | None) -> int:
    parser = _SafeArgumentParser(
        prog="run_live_steamapis_offer_smoke",
        add_help=True,
    )
    parser.add_argument(
        "--seconds",
        type=_duration,
        default=DEFAULT_DURATION_SECONDS,
        metavar="INTEGER",
    )
    return int(parser.parse_args(argv).seconds)


def _gate_enabled(environ: Mapping[str, str]) -> bool:
    return environ.get(RUN_GATE_ENV, "").strip().casefold() == "true"


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


async def async_main(
    *,
    seconds: int = DEFAULT_DURATION_SECONDS,
    environ: Mapping[str, str] | None = None,
    printer: Callable[[str], None] = print,
    client_factory: Callable[[SteamApisWebSocketConfig], SteamApisWebSocketClient] = (
        SteamApisWebSocketClient
    ),
    pool_factory: Callable[..., SteamApisOfferPool] = SteamApisOfferPool,
    session_runner: Callable[..., Awaitable[object]] = run_steamapis_offer_session,
    timeout_factory: Callable[[float | None], Any] = asyncio.timeout,
) -> int:
    """Run one explicitly enabled bounded SteamApis offer smoke."""

    if type(seconds) is not int or not (
        MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS
    ):
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: invalid_duration",
        )
        return 2

    environ = os.environ if environ is None else environ
    if not _gate_enabled(environ):
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: opt_in_disabled",
        )
        return 0

    api_key_value = environ.get(API_KEY_ENV)
    if api_key_value is None or not api_key_value.strip():
        _print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: api_key_missing",
        )
        return 1
    api_key = api_key_value.strip()

    try:
        client = client_factory(SteamApisWebSocketConfig(api_key=api_key))
        pool = pool_factory(max_size=SMOKE_POOL_MAX_SIZE, ttl=SMOKE_POOL_TTL)
        timeout_context = timeout_factory(seconds)
        try:
            async with timeout_context:
                await session_runner(client=client, pool=pool)
        except TimeoutError:
            if not timeout_context.expired():
                raise
            stop_reason = "timeout"
        else:
            stop_reason = "normal_close"
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception:
        _print_lines(
            printer,
            "live_smoke_executed: yes",
            "result: failed",
            "reason: session_failed",
        )
        return 1

    try:
        snapshot = pool.snapshot()
        retained_observations = len(snapshot.observations)
        retained_added = sum(
            observation.event_type is SteamApisListingEventType.ADDED
            for observation in snapshot.observations
        )
        retained_updated = sum(
            observation.event_type is SteamApisListingEventType.UPDATED
            for observation in snapshot.observations
        )
        if retained_observations != retained_added + retained_updated:
            raise RuntimeError
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception:
        _print_lines(
            printer,
            "live_smoke_executed: yes",
            "result: failed",
            "reason: snapshot_failed",
        )
        return 1

    if retained_observations == 0:
        _print_lines(
            printer,
            "live_smoke_executed: yes",
            "result: failed",
            "reason: no_retained_observations",
            f"stop_reason: {stop_reason}",
            f"duration_seconds: {seconds}",
            "retained_observations: 0",
            "retained_added: 0",
            "retained_updated: 0",
        )
        return 1

    _print_lines(
        printer,
        "live_smoke_executed: yes",
        "result: success",
        f"stop_reason: {stop_reason}",
        f"duration_seconds: {seconds}",
        f"retained_observations: {retained_observations}",
        f"retained_added: {retained_added}",
        f"retained_updated: {retained_updated}",
    )
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    """Parse CLI input and run the bounded live smoke."""

    try:
        seconds = _parse_arguments(argv)
    except _InvalidArguments:
        _print_lines(
            print,
            "live_smoke_executed: no",
            "reason: invalid_duration",
        )
        raise SystemExit(2) from None
    raise SystemExit(asyncio.run(async_main(seconds=seconds)))


if __name__ == "__main__":
    main()
