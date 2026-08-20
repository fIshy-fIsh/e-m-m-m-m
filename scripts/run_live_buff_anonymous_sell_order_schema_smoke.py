from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.buff_anonymous_listing_client import (
    BUFF_ANONYMOUS_BASE_URL,
    BUFF_ANONYMOUS_SELL_ORDER_PATH,
    BUFF_ANONYMOUS_USER_AGENT,
)
from app.services.buff_listing_provider import (
    BuffListingProvider,
    BuffListingProviderError,
)
from scripts.buff_listing_smoke_utils import (
    BuffListingSmokeRequestState,
    BuffListingSmokeRuntime,
    BuffListingSmokeRuntimeFactory,
    budget_was_exceeded,
    create_buff_listing_smoke_runtime,
    is_exact_success_state,
    print_lines,
    try_read_request_state,
)
from scripts.steamdt_smoke_utils import parse_bool_env

RUN_GATE_ENV = "BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE"
GOODS_ID_ENV = "BUFF_READONLY_SMOKE_GOODS_ID"
BASE_URL = BUFF_ANONYMOUS_BASE_URL
ENDPOINT_PATH = BUFF_ANONYMOUS_SELL_ORDER_PATH
USER_AGENT = BUFF_ANONYMOUS_USER_AGENT
BuffAnonymousSchemaRequestState = BuffListingSmokeRequestState
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

_REASON_MAP = {
    "response_not_json": "response_not_json",
    "response_schema_invalid": "response_schema_invalid",
    "anonymous_access_unavailable": "anonymous_access_unavailable",
    "items_missing": "items_missing",
    "listing_id_invalid": "listing_id_missing",
    "price_invalid": "price_invalid",
    "paintwear_invalid": "paintwear_invalid",
    "asset_id_invalid": "response_schema_invalid",
    "paintseed_invalid": "response_schema_invalid",
    "request_failed": "request_failed",
    "invalid_goods_id": "goods_id_invalid",
}


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: BuffListingSmokeRuntimeFactory | None = None,
) -> int:
    """Run one explicitly enabled anonymous BUFF schema request."""

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
                        "anonymous_request: yes",
                        "cookie_used: no",
                        "login_used: no",
                        "page_num: 1",
                        "item_list_present: yes",
                        "listing_item_present: yes",
                        "listing_id_present: yes",
                        "price_valid: yes",
                        "paintwear_valid: yes",
                        "asset_id_present: yes",
                        f"paintseed_present: {'yes' if first.paintseed is not None else 'no'}",
                    ]
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
            except BuffListingProviderError as exc:
                failure = _REASON_MAP.get(exc.reason, "response_schema_invalid")
                state = try_read_request_state(runtime)
                if state is None:
                    failure = "request_count_invalid"
                elif budget_was_exceeded(state):
                    failure = "request_count_invalid"
            except Exception:
                failure = "request_failed"
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
