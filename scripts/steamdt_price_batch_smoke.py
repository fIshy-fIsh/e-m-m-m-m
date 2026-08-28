# ruff: noqa: I001
import os
from decimal import Decimal

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
if __package__:
    from .steamdt_smoke_utils import (
        MAX_STEAMDT_SMOKE_BATCH_NAMES,
        is_explicit_false,
        parse_bool_env,
        parse_decimal_env,
        parse_market_hash_names,
        print_guard_exit,
        safe_error_message,
        summarize_quote_raw,
    )
else:
    from steamdt_smoke_utils import (
        MAX_STEAMDT_SMOKE_BATCH_NAMES,
        is_explicit_false,
        parse_bool_env,
        parse_decimal_env,
        parse_market_hash_names,
        print_guard_exit,
        safe_error_message,
        summarize_quote_raw,
    )


async def _run() -> None:
    environ = os.environ
    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = environ.get("STEAMDT_API_KEY")
    market_hash_names_raw = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAMES")
    avg_sanity_enabled = parse_bool_env(environ, "STEAMDT_ENABLE_AVG_SANITY_CHECK")
    fallback_to_lowest_positive = parse_bool_env(
        environ,
        "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE",
    )

    if not is_explicit_false(environ, "STEAMDT_DRY_RUN"):
        print_guard_exit(
            print,
            "SteamDT batch smoke request skipped: STEAMDT_DRY_RUN is not false.",
        )
        return
    if not api_key:
        print_guard_exit(print, "SteamDT batch smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_names_raw:
        print_guard_exit(
            print,
            "SteamDT batch smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAMES is missing.",
        )
        return

    names = parse_market_hash_names(market_hash_names_raw)
    if not names:
        print_guard_exit(
            print,
            "SteamDT batch smoke request skipped: no valid market hash names were provided.",
        )
        return
    if len(names) > MAX_STEAMDT_SMOKE_BATCH_NAMES:
        print_guard_exit(
            print,
            "SteamDT batch smoke request skipped: maximum 10 market hash names are allowed.",
        )
        return

    max_price_to_avg_ratio: Decimal | None = None
    selection_config = None
    if avg_sanity_enabled:
        try:
            max_price_to_avg_ratio = parse_decimal_env(
                environ,
                "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
                "1.50",
            )
            selection_config = SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=max_price_to_avg_ratio,
                fallback_to_lowest_positive=fallback_to_lowest_positive,
            )
        except ValueError as exc:
            print_guard_exit(print, f"SteamDT batch smoke request skipped: {exc}")
            return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    avg_prices_by_name: dict[str, Decimal] | None = None
    avg_price_failed_count = 0
    if avg_sanity_enabled:
        avg_prices_by_name = {}
        for name in names:
            try:
                avg_result = await client.get_avg_price(name)
            except Exception as exc:
                avg_price_failed_count += 1
                print(
                    "SteamDT batch avg sanity request failed; selection skipped: "
                    f"market_hash_name={name}, "
                    f"error={safe_error_message(exc, api_key=api_key)}"
                )
                print(f"avg price failed count: {avg_price_failed_count}")
                return
            if avg_result.avg_price_cny is not None:
                avg_prices_by_name[name] = avg_result.avg_price_cny

    try:
        result = await client.get_price_batch_with_selection(
            names,
            selection_config=selection_config,
            avg_prices_by_name=avg_prices_by_name,
        )
    except Exception as exc:
        print(
            "SteamDT batch smoke request failed: "
            f"{safe_error_message(exc, api_key=api_key)}"
        )
        return

    print("smoke script: steamdt_price_batch_smoke")
    print("smoke mode: batch")
    print(f"requested count: {len(names)}")
    print(f"quote count: {len(result.quotes)}")
    print(f"missing count: {len(result.missing)}")
    print(f"avg sanity enabled: {avg_sanity_enabled}")
    print(f"avg prices found count: {0 if avg_prices_by_name is None else len(avg_prices_by_name)}")
    print(f"avg price failed count: {avg_price_failed_count}")
    print(f"max_price_to_avg_ratio: {max_price_to_avg_ratio}")
    print(f"fallback_to_lowest_positive: {fallback_to_lowest_positive}")
    for quote in result.quotes.values():
        raw_summary = summarize_quote_raw(quote.raw)
        print(
            f"quote: market_hash_name={quote.market_hash_name}, "
            f"price_cny={quote.price_cny}, "
            f"source={quote.source}, "
            f"selected_strategy={raw_summary['selected_strategy']}, "
            f"reason_codes={raw_summary['reason_codes']}, "
            f"selected_platform={raw_summary['selected_platform']}, "
            f"candidate_count={raw_summary['candidate_count']}"
        )
    print(f"missing names: {result.missing}")


def main() -> None:
    """Run a manual official read-only SteamDT price-batch smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAMES=
    "AK-47 | Redline (Field-Tested),AWP | Asiimov (Field-Tested)"
    # Optional avg sanity check:
    $env:STEAMDT_ENABLE_AVG_SANITY_CHECK="true"
    $env:STEAMDT_MAX_PRICE_TO_AVG_RATIO="1.50"
    $env:STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE="false"
    py -3.13 scripts/steamdt_price_batch_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAMES=
    "AK-47 | Redline (Field-Tested),AWP | Asiimov (Field-Tested)" \
    STEAMDT_ENABLE_AVG_SANITY_CHECK=true \
    STEAMDT_MAX_PRICE_TO_AVG_RATIO=1.50 \
    STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE=false \
    py -3.13 scripts/steamdt_price_batch_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
