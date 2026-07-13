import asyncio
import os
from collections.abc import Callable, Mapping
from typing import Any

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.price_provider import (
    PriceLookupResult,
    PriceQuote,
    SteamDTPriceProvider,
    SteamDTPriceProviderConfig,
)
from scripts.steamdt_smoke_utils import (
    MAX_STEAMDT_SMOKE_BATCH_NAMES,
    is_explicit_false,
    parse_bool_env,
    parse_decimal_env,
    parse_int_env,
    parse_market_hash_names,
    print_guard_exit,
    redact_message,
    safe_error_message,
    summarize_quote_raw,
)


def build_provider_config_from_env(
    environ: Mapping[str, str],
) -> SteamDTPriceProviderConfig:
    """Build provider and selector config from smoke-script environment variables."""

    selection_config = SteamDTPriceSelectionConfig(
        max_price_to_avg_ratio=parse_decimal_env(
            environ,
            "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
            "1.50",
        ),
        fallback_to_lowest_positive=parse_bool_env(
            environ,
            "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE",
        ),
    )
    return SteamDTPriceProviderConfig(
        selection_config=selection_config,
        enable_avg_sanity_check=parse_bool_env(
            environ,
            "STEAMDT_ENABLE_AVG_SANITY_CHECK",
        ),
        fail_closed_on_avg_error=True,
        max_avg_requests_per_batch=parse_int_env(
            environ,
            "STEAMDT_PROVIDER_MAX_AVG_REQUESTS_PER_BATCH",
            "10",
        ),
    )


def summarize_price_quote(quote: PriceQuote) -> list[str]:
    """Return safe summary lines for one provider quote without raw payload dumps."""

    raw_summary = summarize_quote_raw(quote.raw)
    return [
        f"market_hash_name: {quote.market_hash_name}",
        f"price_cny: {quote.price_cny}",
        f"source: {quote.source}",
        f"selected_strategy: {raw_summary['selected_strategy']}",
        f"reason_codes: {raw_summary['reason_codes']}",
        f"selected_platform: {raw_summary['selected_platform']}",
        f"candidate_count: {raw_summary['candidate_count']}",
    ]


def summarize_price_lookup_result(
    result: PriceLookupResult,
    *,
    api_key: str | None = None,
) -> list[str]:
    """Return safe summary lines for a provider batch lookup result."""

    lines = [
        f"quote count: {len(result.quotes)}",
        f"missing count: {len(result.missing)}",
        f"errors count: {len(result.errors)}",
    ]
    for quote in result.quotes.values():
        raw_summary = summarize_quote_raw(quote.raw)
        lines.append(
            "quote: "
            f"market_hash_name={quote.market_hash_name}, "
            f"price_cny={quote.price_cny}, "
            f"source={quote.source}, "
            f"selected_strategy={raw_summary['selected_strategy']}, "
            f"reason_codes={raw_summary['reason_codes']}, "
            f"selected_platform={raw_summary['selected_platform']}, "
            f"candidate_count={raw_summary['candidate_count']}"
        )
    lines.append(f"missing names: {result.missing}")
    lines.append(
        "errors summary: "
        f"{[redact_message(error, api_key=api_key) for error in result.errors]}"
    )
    return lines


async def run_provider_smoke(
    environ: Mapping[str, str] | None = None,
    *,
    client_factory: Callable[[SteamDTClientConfig], Any] | None = None,
    provider_factory: Callable[[Any, SteamDTPriceProviderConfig], Any] | None = None,
    printer: Callable[[str], None] = print,
) -> int:
    """Run the manual provider smoke flow with injectable factories for tests."""

    environ = os.environ if environ is None else environ
    client_factory = client_factory or (lambda config: SteamDTHttpClient(config))
    provider_factory = provider_factory or (
        lambda client, config: SteamDTPriceProvider(client, config)
    )

    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = environ.get("STEAMDT_API_KEY")
    batch_mode = parse_bool_env(environ, "STEAMDT_PROVIDER_BATCH_MODE")
    avg_sanity_enabled = parse_bool_env(environ, "STEAMDT_ENABLE_AVG_SANITY_CHECK")

    if not is_explicit_false(environ, "STEAMDT_DRY_RUN"):
        return print_guard_exit(
            printer,
            "SteamDT provider smoke request skipped: STEAMDT_DRY_RUN is not false.",
        )
    if not api_key:
        return print_guard_exit(
            printer,
            "SteamDT provider smoke request skipped: STEAMDT_API_KEY is missing.",
        )

    if batch_mode:
        names = parse_market_hash_names(environ.get("STEAMDT_SMOKE_MARKET_HASH_NAMES"))
        if not names:
            return print_guard_exit(
                printer,
                "SteamDT provider batch smoke request skipped: "
                "STEAMDT_SMOKE_MARKET_HASH_NAMES is missing.",
            )
        if len(names) > MAX_STEAMDT_SMOKE_BATCH_NAMES:
            return print_guard_exit(
                printer,
                "SteamDT provider batch smoke request skipped: "
                "maximum 10 market hash names are allowed.",
            )
    else:
        market_hash_name = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAME")
        if market_hash_name is None or not market_hash_name.strip():
            return print_guard_exit(
                printer,
                "SteamDT provider smoke request skipped: "
                "STEAMDT_SMOKE_MARKET_HASH_NAME is missing.",
            )
        names = [market_hash_name.strip()]

    try:
        provider_config = build_provider_config_from_env(environ)
    except ValueError as exc:
        return print_guard_exit(printer, f"SteamDT provider smoke request skipped: {exc}")

    client = client_factory(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )
    provider = provider_factory(client, provider_config)

    if batch_mode:
        try:
            result = await provider.get_prices(names)
        except Exception as exc:
            printer(
                "SteamDT provider batch smoke request failed: "
                f"{safe_error_message(exc, api_key=api_key)}"
            )
            return 1
        printer("smoke script: steamdt_provider_price_smoke")
        printer("smoke mode: provider_batch")
        printer(f"requested count: {len(names)}")
        printer(f"avg sanity enabled: {avg_sanity_enabled}")
        for line in summarize_price_lookup_result(result, api_key=api_key):
            printer(line)
        return 0

    try:
        quote = await provider.get_price(names[0])
    except Exception as exc:
        printer(
            "SteamDT provider smoke request failed: "
            f"{safe_error_message(exc, api_key=api_key)}"
        )
        return 1

    printer("smoke script: steamdt_provider_price_smoke")
    printer("smoke mode: provider_single")
    for line in summarize_price_quote(quote):
        printer(line)
    printer(f"avg sanity enabled: {avg_sanity_enabled}")
    return 0


def main() -> None:
    """Run a manual official read-only SteamDT provider smoke test.

    Default behavior is dry-run and does not make real SteamDT requests. Set
    STEAMDT_DRY_RUN=false and STEAMDT_API_KEY explicitly before manual use.
    """

    asyncio.run(run_provider_smoke())


if __name__ == "__main__":
    main()
