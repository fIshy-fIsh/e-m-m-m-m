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

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionResult,
)
from app.services.live_recipe_valuation import (
    LiveRecipeValuationRejection,
    LiveRecipeValuationRejectionReason,
    LiveRecipeValuationResult,
    LiveValuedOpportunity,
)
from app.services.recipe_solver import ConstructedRecipe
from app.services.steamdt_buff_live_recipe_fixture import (
    STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME,
    SteamDTBuffLiveRecipeFixture,
    build_verified_steamdt_buff_live_recipe_fixture,
)
from app.services.steamdt_buff_live_recipe_valuation import (
    value_live_recipes_with_steamdt_buff_prices,
)
from app.services.steamdt_market_data import SteamDTMarketDataClient
from app.services.tradeup_engine import InputItem, TradeupResult
from scripts.steamdt_smoke_utils import parse_bool_env

RUN_GATE_ENV = "STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE"
API_KEY_ENV = "STEAMDT_API_KEY"
BASE_URL_ENV = "STEAMDT_BASE_URL"
DEFAULT_BASE_URL = "https://open.steamdt.com"

_REJECTION_REASON_MAP = {
    LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR: "price_provider_error",
    LiveRecipeValuationRejectionReason.MISSING_OUTPUT_PRICE: "missing_output_price",
    LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT: (
        "invalid_valuation_result"
    ),
}


class SteamDTBuffLiveRecipeValuationSmokeRuntime(Protocol):
    @property
    def client(self) -> SteamDTMarketDataClient:
        """Return the borrowed aggregate market-data client."""

    @property
    def request_count(self) -> int:
        """Return the number of attempted outbound SteamDT requests."""

    async def aclose(self) -> None:
        """Close every resource owned by the smoke runtime."""


class SteamDTBuffLiveRecipeValuationSmokeRuntimeFactory(Protocol):
    def __call__(
        self,
        base_url: str,
        api_key: str,
    ) -> Awaitable[SteamDTBuffLiveRecipeValuationSmokeRuntime]:
        """Create an owned one-attempt SteamDT valuation runtime."""


class _RequestBudgetExceeded(RuntimeError):
    """A second outbound attempt exceeded the smoke request budget."""


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
) -> SteamDTBuffLiveRecipeValuationSmokeRuntime:
    request_counter = [0]

    async def count_request(_request: httpx.Request) -> None:
        request_counter[0] += 1
        if request_counter[0] > 1:
            raise _RequestBudgetExceeded

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
    except BaseException as exc:
        try:
            await http_client.aclose()
        except Exception:
            raise exc from None
        raise
    return _HttpSmokeRuntime(_client=client, _request_counter=request_counter)


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: (
        SteamDTBuffLiveRecipeValuationSmokeRuntimeFactory | None
    ) = None,
) -> int:
    """Run one explicitly enabled full SteamDT BUFF recipe valuation."""

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
    base_url = environ.get(BASE_URL_ENV, DEFAULT_BASE_URL)

    try:
        fixture_value = build_verified_steamdt_buff_live_recipe_fixture()
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception:
        return _print_fixture_failure(printer, "fixture_invalid")

    fixture, fixture_failure = _validate_fixture(fixture_value)
    if fixture_failure is not None or fixture is None:
        return _print_fixture_failure(
            printer,
            fixture_failure or "fixture_invalid",
        )

    runtime: SteamDTBuffLiveRecipeValuationSmokeRuntime | None = None
    request_count: int | None = 0
    success_lines: list[str] = []
    failure_reason: str | None = None
    try:
        create_runtime = runtime_factory or _create_http_smoke_runtime
        try:
            runtime = await create_runtime(base_url, api_key)
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            failure_reason = "runtime_failed"

        if runtime is not None:
            try:
                valuation = await value_live_recipes_with_steamdt_buff_prices(
                    construction_result=fixture.construction_result,
                    client=runtime.client,
                    solver_config=fixture.solver_config,
                    risk_config=fixture.risk_config,
                )
                failure_reason, risk_passed = _classify_valuation_result(
                    valuation,
                    fixture,
                )
                request_count = _try_read_request_count(runtime)
                if failure_reason is None:
                    if request_count != 1 or risk_passed is None:
                        failure_reason = "request_count_invalid"
                    else:
                        success_lines = _success_lines(risk_passed)
                elif request_count is not None and request_count > 1:
                    failure_reason = "request_count_invalid"
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                failure_reason = "valuation_failed"
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


def _validate_fixture(
    value: object,
) -> tuple[SteamDTBuffLiveRecipeFixture | None, str | None]:
    try:
        if type(value) is not SteamDTBuffLiveRecipeFixture:
            return None, "fixture_invalid"
        construction = value.construction_result
        if (
            type(construction) is not LiveRecipeConstructionResult
            or type(construction.recipes) is not tuple
        ):
            return None, "fixture_invalid"
        if len(construction.recipes) != 1:
            return None, "recipe_count_invalid"

        live_recipe = construction.recipes[0]
        if type(live_recipe) is not LiveConstructedRecipe:
            return None, "fixture_invalid"
        recipe = live_recipe.recipe
        if (
            type(recipe) is not ConstructedRecipe
            or type(recipe.input_items) is not tuple
        ):
            return None, "fixture_invalid"
        if len(recipe.input_items) != 10:
            return None, "input_count_invalid"
        if any(type(item) is not InputItem for item in recipe.input_items):
            return None, "fixture_invalid"
        if (
            type(live_recipe.selected_source_offer_ids) is not tuple
            or len(live_recipe.selected_source_offer_ids) != 10
            or any(
                type(source_id) is not str or not source_id
                for source_id in live_recipe.selected_source_offer_ids
            )
            or len(set(live_recipe.selected_source_offer_ids)) != 10
            or type(recipe.paint_seeds) is not tuple
            or len(recipe.paint_seeds) != 10
            or any(type(seed) is not int for seed in recipe.paint_seeds)
        ):
            return None, "fixture_invalid"
        if type(recipe.tradeup_results) is not tuple:
            return None, "fixture_invalid"

        output_names: set[str] = set()
        for result in recipe.tradeup_results:
            if (
                type(result) is not TradeupResult
                or type(result.output_market_hash_name) is not str
            ):
                return None, "fixture_invalid"
            output_names.add(result.output_market_hash_name)
        if len(output_names) != 1:
            return None, "output_count_invalid"
        if len(recipe.tradeup_results) != 1:
            return None, "fixture_invalid"
        if (
            next(iter(output_names))
            != STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
        ):
            return None, "fixture_invalid"
        return value, None
    except MemoryError:
        raise
    except Exception:
        return None, "fixture_invalid"


def _classify_valuation_result(
    value: object,
    fixture: SteamDTBuffLiveRecipeFixture,
) -> tuple[str | None, bool | None]:
    try:
        if type(value) is not LiveRecipeValuationResult:
            return "valuation_result_invalid", None
        if type(value.opportunities) is not tuple or type(value.rejected) is not tuple:
            return "valuation_result_invalid", None

        live_recipe = fixture.construction_result.recipes[0]
        if len(value.opportunities) == 1 and not value.rejected:
            opportunity = value.opportunities[0]
            if type(opportunity) is not LiveValuedOpportunity:
                return "valuation_result_invalid", None
            if (
                opportunity.recipe != live_recipe.recipe
                or opportunity.selected_source_offer_ids
                != live_recipe.selected_source_offer_ids
                or type(opportunity.valued_tradeup_results) is not tuple
                or len(opportunity.valued_tradeup_results) != 1
            ):
                return "valuation_result_invalid", None

            original = live_recipe.recipe.tradeup_results[0]
            valued = opportunity.valued_tradeup_results[0]
            if (
                type(valued) is not TradeupResult
                or valued.output_market_hash_name
                != original.output_market_hash_name
                or valued.probability != original.probability
                or valued.output_float != original.output_float
                or valued.output_wear != original.output_wear
                or type(opportunity.risk_decision.passed) is not bool
            ):
                return "valuation_result_invalid", None
            return None, opportunity.risk_decision.passed

        if not value.opportunities and len(value.rejected) == 1:
            rejection = value.rejected[0]
            if (
                type(rejection) is not LiveRecipeValuationRejection
                or rejection.selected_source_offer_ids
                != live_recipe.selected_source_offer_ids
                or type(rejection.reason_code)
                is not LiveRecipeValuationRejectionReason
            ):
                return "valuation_result_invalid", None
            reason = _REJECTION_REASON_MAP.get(rejection.reason_code)
            if reason is None:
                return "valuation_result_invalid", None
            return reason, None

        return "valuation_result_invalid", None
    except MemoryError:
        raise
    except Exception:
        return "valuation_result_invalid", None


def _read_request_count(
    runtime: SteamDTBuffLiveRecipeValuationSmokeRuntime,
) -> int:
    request_count = runtime.request_count
    if type(request_count) is not int or request_count < 0:
        raise TypeError("SteamDT valuation smoke runtime returned an invalid request count")
    return request_count


def _try_read_request_count(
    runtime: SteamDTBuffLiveRecipeValuationSmokeRuntime,
) -> int | None:
    try:
        return _read_request_count(runtime)
    except MemoryError:
        raise
    except Exception:
        return None


def _print_fixture_failure(
    printer: Callable[[str], None],
    reason: str,
) -> int:
    _print_lines(
        printer,
        "live_smoke_executed: no",
        "result: failed",
        f"reason: {reason}",
        "SteamDT requests sent: 0",
    )
    return 1


def _success_lines(risk_passed: bool) -> list[str]:
    return [
        "live_smoke_executed: yes",
        "result: success",
        "construction_source: deterministic_versioned_fixture",
        "recipe_count: 1",
        "input_count: 10",
        "distinct_output_count: 1",
        "valuation_opportunities: 1",
        "valuation_rejections: 0",
        "price_source_path: steamdt:buff",
        "ev_evaluated: yes",
        "roi_evaluated: yes",
        "risk_evaluated: yes",
        f"risk_passed: {'yes' if risk_passed else 'no'}",
    ]


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def main() -> None:
    """Run the explicitly enabled one-request full valuation smoke."""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
