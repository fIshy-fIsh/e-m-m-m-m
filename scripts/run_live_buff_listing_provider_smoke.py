from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buff_listing_provider import BuffListingProvider, BuffListingProviderError
from scripts.buff_listing_smoke_utils import (
    BuffListingSmokeRuntime,
    BuffListingSmokeRuntimeFactory,
    budget_was_exceeded,
    create_buff_listing_smoke_runtime,
    is_exact_success_state,
    print_lines,
    try_read_request_state,
)
from scripts.steamdt_smoke_utils import parse_bool_env

RUN_GATE_ENV = "BUFF_RUN_LISTING_PROVIDER_SMOKE"
GOODS_ID_ENV = "BUFF_READONLY_SMOKE_GOODS_ID"


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: BuffListingSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicitly enabled BUFF listing-provider request."""

    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_GATE_ENV):
        print_lines(
            printer,
            "live_smoke_executed: no",
            "reason: opt_in_disabled",
            "BUFF requests sent: 0",
        )
        return 0
    goods_value = environ.get(GOODS_ID_ENV)
    if goods_value is None or (type(goods_value) is str and not goods_value.strip()):
        return _guard_failure(printer, "goods_id_missing")
    if type(goods_value) is not str:
        return _guard_failure(printer, "goods_id_invalid")
    goods_id = goods_value.strip()

    runtime: BuffListingSmokeRuntime | None = None
    state = None
    failure: str | None = None
    success: list[str] = []
    try:
        factory = runtime_factory or create_buff_listing_smoke_runtime
        try:
            runtime = await factory(goods_id)
            if runtime is None:
                failure = "runtime_failed"
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            failure = "runtime_failed"

        if runtime is not None:
            try:
                listings = await BuffListingProvider(runtime.client).get_listings(goods_id)
                if not listings:
                    failure = "no_items"
                else:
                    first = listings[0]
                    success = [
                        "live_smoke_executed: yes",
                        "result: success",
                        f"listing_count: {len(listings)}",
                        "first_listing_id_present: yes",
                        "first_listing_price_valid: yes",
                        "first_listing_paintwear_valid: yes",
                    ]
                    del first
                state = try_read_request_state(runtime)
                if state is None:
                    failure = "request_count_invalid"
                    success = []
                elif failure is None and not is_exact_success_state(state):
                    failure = "request_count_invalid"
                    success = []
                elif budget_was_exceeded(state):
                    failure = "request_count_invalid"
                    success = []
            except (MemoryError, asyncio.CancelledError):
                raise
            except BuffListingProviderError:
                failure = "provider_failed"
                state = try_read_request_state(runtime)
                if state is None:
                    failure = "request_count_invalid"
                elif budget_was_exceeded(state):
                    failure = "request_count_invalid"
            except Exception:
                failure = "provider_failed"
                state = try_read_request_state(runtime)
                if state is None:
                    failure = "request_count_invalid"
                elif budget_was_exceeded(state):
                    failure = "request_count_invalid"
    finally:
        if runtime is not None:
            try:
                await runtime.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                failure = "close_failed"
                success = []

    dispatched = None if state is None else state.dispatched
    if failure is not None:
        print_lines(
            printer,
            "live_smoke_executed: yes" if runtime is not None else "live_smoke_executed: no",
            "result: failed",
            f"reason: {failure}",
            f"BUFF requests sent: {'unavailable' if dispatched is None else dispatched}",
        )
        return 1
    print_lines(printer, *success, f"BUFF requests sent: {dispatched}")
    return 0


def _guard_failure(printer: Callable[[str], None], reason: str) -> int:
    print_lines(
        printer,
        "live_smoke_executed: no",
        f"reason: {reason}",
        "BUFF requests sent: 0",
    )
    return 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
