import os
from decimal import Decimal

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from scripts.steamdt_smoke_utils import (
    is_explicit_false,
    parse_bool_env,
    parse_decimal_env,
    print_guard_exit,
    safe_error_message,
    summarize_quote_raw,
)


async def _run() -> None:
    environ = os.environ
    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = environ.get("STEAMDT_API_KEY")
    market_hash_name = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAME")
    avg_sanity_enabled = parse_bool_env(environ, "STEAMDT_ENABLE_AVG_SANITY_CHECK")
    fallback_to_lowest_positive = parse_bool_env(
        environ,
        "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE",
    )

    if not is_explicit_false(environ, "STEAMDT_DRY_RUN"):
        print_guard_exit(
            print,
            "SteamDT single smoke request skipped: STEAMDT_DRY_RUN is not false.",
        )
        return
    if not api_key:
        print_guard_exit(print, "SteamDT single smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if market_hash_name is None or not market_hash_name.strip():
        print_guard_exit(
            print,
            "SteamDT single smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAME is missing.",
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
            print_guard_exit(print, f"SteamDT single smoke request skipped: {exc}")
            return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    avg_price_cny: Decimal | None = None
    if avg_sanity_enabled:
        try:
            avg_result = await client.get_avg_price(market_hash_name.strip())
        except Exception as exc:
            print(
                "SteamDT single avg sanity request failed; selection skipped: "
                f"{safe_error_message(exc, api_key=api_key)}"
            )
            return
        avg_price_cny = avg_result.avg_price_cny

    try:
        quote = await client.get_price_single_with_selection(
            market_hash_name.strip(),
            selection_config=selection_config,
            avg_price_cny=avg_price_cny,
        )
    except Exception as exc:
        print(f"SteamDT single smoke request failed: {safe_error_message(exc, api_key=api_key)}")
        return

    raw_summary = summarize_quote_raw(quote.raw)
    print("smoke script: steamdt_price_single_smoke")
    print("smoke mode: single")
    print(f"market_hash_name: {quote.market_hash_name}")
    print(f"price_cny: {quote.price_cny}")
    print(f"source: {quote.source}")
    print(f"avg sanity enabled: {avg_sanity_enabled}")
    print(f"avg_price_cny: {avg_price_cny}")
    print(f"max_price_to_avg_ratio: {max_price_to_avg_ratio}")
    print(f"fallback_to_lowest_positive: {fallback_to_lowest_positive}")
    print(f"selected_strategy: {raw_summary['selected_strategy']}")
    print(f"reason_codes: {raw_summary['reason_codes']}")
    print(f"selected_platform: {raw_summary['selected_platform']}")
    print(f"candidate_count: {raw_summary['candidate_count']}")


def main() -> None:
    """Run a manual official read-only SteamDT price-single smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)"
    # Optional avg sanity check:
    $env:STEAMDT_ENABLE_AVG_SANITY_CHECK="true"
    $env:STEAMDT_MAX_PRICE_TO_AVG_RATIO="1.50"
    $env:STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE="false"
    py -3.13 scripts/steamdt_price_single_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)" \
    STEAMDT_ENABLE_AVG_SANITY_CHECK=true \
    STEAMDT_MAX_PRICE_TO_AVG_RATIO=1.50 \
    STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE=false \
    py -3.13 scripts/steamdt_price_single_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
