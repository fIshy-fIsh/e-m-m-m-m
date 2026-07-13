import os
from decimal import Decimal, InvalidOperation

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Return true only when an env flag is explicitly set to true."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() == "true"


def _parse_decimal_env(name: str, default: str) -> Decimal:
    """Parse a Decimal env value for smoke-only configuration."""

    raw_value = os.getenv(name, default).strip()
    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal value") from exc


def _safe_error_message(exc: Exception, *, api_key: str | None) -> str:
    """Format an exception without leaking a configured API key."""

    message = str(exc)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message


async def _run() -> None:
    base_url = os.getenv("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = os.getenv("STEAMDT_API_KEY")
    dry_run = os.getenv("STEAMDT_DRY_RUN", "true").lower() != "false"
    market_hash_names_raw = os.getenv("STEAMDT_SMOKE_MARKET_HASH_NAMES")
    avg_sanity_enabled = _env_flag("STEAMDT_ENABLE_AVG_SANITY_CHECK")
    fallback_to_lowest_positive = _env_flag(
        "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE"
    )

    if dry_run:
        print("SteamDT batch smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print("SteamDT batch smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_names_raw:
        print("SteamDT batch smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAMES is missing.")
        return

    names = [name.strip() for name in market_hash_names_raw.split(",") if name.strip()]
    if not names:
        print("SteamDT batch smoke request skipped: no valid market hash names were provided.")
        return
    if len(names) > 10:
        print("SteamDT batch smoke request skipped: maximum 10 market hash names are allowed.")
        return

    max_price_to_avg_ratio: Decimal | None = None
    selection_config = None
    if avg_sanity_enabled:
        try:
            max_price_to_avg_ratio = _parse_decimal_env(
                "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
                "1.50",
            )
            selection_config = SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=max_price_to_avg_ratio,
                fallback_to_lowest_positive=fallback_to_lowest_positive,
            )
        except ValueError as exc:
            print(f"SteamDT batch smoke request skipped: {exc}")
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
                    "SteamDT avg sanity request failed; batch selection skipped: "
                    f"market_hash_name={name}, "
                    f"error={_safe_error_message(exc, api_key=api_key)}"
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
            f"{_safe_error_message(exc, api_key=api_key)}"
        )
        return

    print(f"requested count: {len(names)}")
    print(f"quote count: {len(result.quotes)}")
    print(f"missing count: {len(result.missing)}")
    print(f"avg sanity enabled: {avg_sanity_enabled}")
    print(f"avg prices found count: {0 if avg_prices_by_name is None else len(avg_prices_by_name)}")
    print(f"avg price failed count: {avg_price_failed_count}")
    print(f"max_price_to_avg_ratio: {max_price_to_avg_ratio}")
    print(f"fallback_to_lowest_positive: {fallback_to_lowest_positive}")
    for quote in result.quotes.values():
        raw = quote.raw or {}
        platform_prices = raw.get("platform_prices", [])
        print(
            f"quote: market_hash_name={quote.market_hash_name}, "
            f"price_cny={quote.price_cny}, "
            f"source={quote.source}, "
            f"selected_strategy={raw.get('selected_strategy')}, "
            f"reason_codes={raw.get('reason_codes')}, "
            f"selected_platform={raw.get('selected_platform')}, "
            f"candidate_count={len(platform_prices)}"
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
